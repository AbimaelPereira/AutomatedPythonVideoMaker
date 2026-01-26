import os
import re
from pydub import AudioSegment
from thefuzz import fuzz

class AudioSegmenter:
    def __init__(self, audio_path, srt_path):
        """
        Carrega o áudio e o SRT na memória para processamento rápido.
        """
        if not os.path.exists(audio_path) or not os.path.exists(srt_path):
            raise FileNotFoundError("Áudio ou SRT não encontrados.")

        print(f"[AudioSegmenter] Carregando áudio (pode demorar)...")
        self.audio = AudioSegment.from_file(audio_path)
        
        print(f"[AudioSegmenter] Parseando SRT...")
        self.subtitles = self._parse_srt(srt_path)
        
        # Ponteiro para saber onde paramos na lista de legendas
        self.current_srt_index = 0

    def _parse_srt(self, srt_path):
        """Lê o SRT e transforma em uma lista de dicionários."""
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Regex para extrair blocos de SRT
        # Padrão: Indice -> Timestamp -> Texto
        pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\Z)', re.DOTALL)
        matches = pattern.findall(content)

        subs = []
        for match in matches:
            subs.append({
                "index": int(match[0]),
                "start_ms": self._time_to_ms(match[1]),
                "end_ms": self._time_to_ms(match[2]),
                "text": match[3].replace('\n', ' ').strip()
            })
        return subs

    def _time_to_ms(self, time_str):
        """Converte 00:00:00,000 para milissegundos."""
        h, m, s_full = time_str.split(':')
        s, ms = s_full.split(',')
        return (int(h) * 3600000) + (int(m) * 60000) + (int(s) * 1000) + int(ms)

    def extract_scene_audio(self, scene_text, output_path, similarity_threshold=70):
        """
        Procura o texto da cena nas legendas a partir da última posição,
        define o tempo de inicio e fim, e salva o corte de áudio.
        """
        start_index = self.current_srt_index
        matched_blocks = []
        
        # Normalização simples para comparação
        scene_text_clean = scene_text.lower()

        accumulated_text = ""
        found_start = False
        
        # Percorre as legendas a partir de onde parou
        for i in range(start_index, len(self.subtitles)):
            sub = self.subtitles[i]
            sub_text_clean = sub['text'].lower()
            
            # Lógica de Matching (Busca Sequencial)
            # Verifica se o bloco atual tem alguma relevância com o texto da cena
            # Usamos 'partial_ratio' para ver se o trecho da legenda está dentro do texto da cena
            ratio = fuzz.partial_ratio(sub_text_clean, scene_text_clean)
            
            if ratio >= similarity_threshold:
                if not found_start:
                    found_start = True
                    # Salva onde começou essa cena
                    first_block_index = i 
                
                matched_blocks.append(sub)
                accumulated_text += " " + sub_text_clean
                
                # Se o texto acumulado já "cobriu" quase todo o texto da cena, podemos parar
                # Verificamos se o texto da cena está contido no que já acumulamos
                full_match_ratio = fuzz.token_set_ratio(scene_text_clean, accumulated_text)
                
                # Se a similaridade do conjunto for alta, consideramos que a cena acabou aqui
                if full_match_ratio > 90 and len(accumulated_text) >= len(scene_text_clean) * 0.8:
                    # Atualiza o ponteiro global para a próxima busca começar daqui
                    self.current_srt_index = i + 1 
                    break
            
            elif found_start:
                # Se já tínhamos encontrado o inicio, mas agora o ratio deu baixo, 
                # pode ser que a cena acabou e o SRT passou para a próxima frase.
                # Mas cuidado: às vezes é só uma palavra conectiva. 
                # Vamos simplificar: se achou start e parou de bater, assume fim.
                # (Essa lógica pode ser refinada depois)
                
                # Verifica se o que já pegamos é suficiente
                if len(accumulated_text) > len(scene_text_clean) * 0.6:
                    self.current_srt_index = i
                    break
        
        if not matched_blocks:
            print(f"[AVISO] Não foi possível encontrar trecho correspondente para: '{scene_text[:30]}...'")
            return None

        # Definir Timestamps de Corte
        start_ms = matched_blocks[0]['start_ms']
        end_ms = matched_blocks[-1]['end_ms']
        
        # Adicionar um padding de segurança (ex: 50ms) para não cortar respiração
        start_ms = max(0, start_ms - 50)
        # end_ms = end_ms + 50
        # end_ms pode ser o inicio da próxima legenda, se não existir proxima, deve ser o final do áudio
        if self.current_srt_index < len(self.subtitles):
            next_sub_start = self.subtitles[self.current_srt_index]['start_ms']
            end_ms = min(end_ms + 50, next_sub_start - 1)
        else:
            end_ms = min(end_ms + 50, len(self.audio))

        print(f"[Corte] Cena detectada: {start_ms}ms -> {end_ms}ms | Texto: {matched_blocks[0]['text']}...{matched_blocks[-1]['text']}")

        # Cortar e Salvar
        scene_audio = self.audio[start_ms:end_ms]
        scene_audio.export(output_path, format="mp3")
        
        return output_path