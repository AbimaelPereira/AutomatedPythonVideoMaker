import os
import re
from pydub import AudioSegment
from thefuzz import fuzz
from difflib import SequenceMatcher

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

    def _ms_to_time(self, ms):
        """Converte milissegundos para formato SRT 00:00:00,000."""
        hours = int(ms // 3600000)
        ms %= 3600000
        minutes = int(ms // 60000)
        ms %= 60000
        seconds = int(ms // 1000)
        milliseconds = int(ms % 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def _normalize_text(self, text):
        """
        Normaliza texto para comparação, removendo pontuação, 
        convertendo para minúsculas e removendo espaços extras.
        """
        # Remove pontuação comum
        text = re.sub(r'[,\.!?;:—\-\"\'()]', '', text)
        # Converte para minúsculas
        text = text.lower()
        # Remove espaços múltiplos
        text = ' '.join(text.split())
        return text

    def _generate_srt_segment(self, matched_blocks, start_offset_ms, srt_output_path):
        """
        Gera um arquivo SRT para o segmento cortado, ajustando os timestamps
        para começar em 00:00:00,000.
        """
        srt_content = []
        
        for idx, block in enumerate(matched_blocks, start=1):
            # Ajustar os timestamps para começar do zero
            adjusted_start = block['start_ms'] - start_offset_ms
            adjusted_end = block['end_ms'] - start_offset_ms
            
            # Garantir que não haja timestamps negativos
            adjusted_start = max(0, adjusted_start)
            adjusted_end = max(0, adjusted_end)
            
            # Formatar no padrão SRT
            start_time = self._ms_to_time(adjusted_start)
            end_time = self._ms_to_time(adjusted_end)
            
            srt_content.append(f"{idx}")
            srt_content.append(f"{start_time} --> {end_time}")
            srt_content.append(block['text'])
            srt_content.append("")
        
        # Salvar arquivo
        with open(srt_output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(srt_content))

    def _find_best_match_window(self, scene_text_normalized, start_index=0):
        """
        Usa uma janela deslizante para encontrar a melhor correspondência
        entre o texto da cena e as legendas.
        
        Returns:
            Tupla (start_block_index, end_block_index, confidence_score)
        """
        scene_words = scene_text_normalized.split()
        num_scene_words = len(scene_words)
        
        best_match = None
        best_score = 0
        best_range = (start_index, start_index)
        
        # Janela deslizante através das legendas
        max_window = min(len(self.subtitles) - start_index, num_scene_words + 10)
        
        for window_size in range(num_scene_words - 2, max_window + 1):
            for i in range(start_index, len(self.subtitles) - window_size + 1):
                # Concatena texto da janela
                window_text = ' '.join([
                    self._normalize_text(self.subtitles[j]['text']) 
                    for j in range(i, i + window_size)
                ])
                
                # Calcula similaridade
                ratio = SequenceMatcher(None, scene_text_normalized, window_text).ratio()
                
                # Verifica se todas as palavras da cena estão presentes
                words_found = sum(1 for word in scene_words if word in window_text)
                coverage = words_found / num_scene_words
                
                # Score combinado (ratio + coverage)
                combined_score = (ratio * 0.6) + (coverage * 0.4)
                
                if combined_score > best_score:
                    best_score = combined_score
                    best_range = (i, i + window_size - 1)
                    best_match = window_text
        
        return best_range[0], best_range[1], best_score, best_match

    def _find_scene_boundaries_v2(self, scene_text, start_index):
        """
        Algoritmo melhorado para encontrar os limites exatos da cena.
        
        Estratégia:
        1. Normaliza o texto da cena e das legendas
        2. Usa janela deslizante para encontrar melhor match
        3. Garante que todos os tokens importantes sejam capturados
        """
        scene_normalized = self._normalize_text(scene_text)
        scene_words = scene_normalized.split()
        
        print(f"[Debug] Procurando por: '{scene_normalized}'")
        print(f"[Debug] Palavras esperadas: {scene_words}")
        
        # Encontra o melhor match usando janela deslizante
        start_block, end_block, score, matched_text = self._find_best_match_window(
            scene_normalized, start_index
        )
        
        print(f"[Debug] Melhor match encontrado: índices {start_block} até {end_block}")
        print(f"[Debug] Score: {score:.2f}")
        print(f"[Debug] Texto matched: '{matched_text}'")
        
        # Verifica se o score é aceitável
        if score < 0.6:
            print(f"[AVISO] Score de matching baixo ({score:.2f}). Tentando busca linear...")
            # Fallback para busca linear
            return self._find_scene_boundaries_linear(scene_text, start_index)
        
        # Extrai os blocos matched
        matched_blocks = []
        for i in range(start_block, end_block + 1):
            matched_blocks.append(self.subtitles[i])
        
        return matched_blocks, end_block + 1

    def _find_scene_boundaries_linear(self, scene_text, start_index):
        """
        Método de fallback: busca linear palavra por palavra.
        Garante capturar todo o texto, mesmo com pontuação diferente.
        """
        scene_normalized = self._normalize_text(scene_text)
        scene_words = scene_normalized.split()
        
        matched_blocks = []
        words_found = []
        current_index = start_index
        
        # Tenta encontrar cada palavra da cena nas legendas
        for target_word in scene_words:
            found = False
            # Busca a partir do índice atual
            for i in range(current_index, len(self.subtitles)):
                sub_text_norm = self._normalize_text(self.subtitles[i]['text'])
                
                if target_word in sub_text_norm or fuzz.ratio(target_word, sub_text_norm) > 80:
                    matched_blocks.append(self.subtitles[i])
                    words_found.append(self.subtitles[i]['text'])
                    current_index = i + 1
                    found = True
                    break
            
            if not found:
                # Se não encontrou a palavra, para aqui
                print(f"[AVISO] Palavra '{target_word}' não encontrada após índice {current_index}")
                break
        
        print(f"[Debug] Busca linear encontrou: {' '.join(words_found)}")
        
        if not matched_blocks:
            return None, start_index
        
        return matched_blocks, current_index

    def extract_scene_audio(self, scene_text, output_path, method='auto'):
        """
        Procura o texto da cena nas legendas e extrai o áudio correspondente.
        
        Args:
            scene_text: Texto da cena a ser procurado
            output_path: Caminho para salvar o arquivo de áudio
            method: 'auto', 'window', ou 'linear'
            
        Returns:
            Tupla (audio_path, srt_path) ou (None, None) se não encontrar
        """
        start_index = self.current_srt_index
        
        print(f"\n{'='*60}")
        print(f"[Segmentação] Iniciando busca a partir do índice {start_index}")
        print(f"[Segmentação] Texto da cena: '{scene_text}'")
        
        # Escolhe o método de busca
        if method == 'linear':
            result = self._find_scene_boundaries_linear(scene_text, start_index)
        else:  # 'auto' ou 'window'
            result = self._find_scene_boundaries_v2(scene_text, start_index)
        
        if result is None or result[0] is None:
            print(f"[ERRO] Não foi possível encontrar correspondência para: '{scene_text[:50]}...'")
            return None, None
        
        matched_blocks, next_index = result
        
        if not matched_blocks:
            print(f"[ERRO] Nenhum bloco encontrado")
            return None, None
        
        # Atualiza o ponteiro global
        self.current_srt_index = next_index
        
        # Define timestamps de corte
        start_ms = matched_blocks[0]['start_ms']
        end_ms = matched_blocks[-1]['end_ms']
        
        # Padding de segurança (50ms antes e depois)
        start_ms = max(0, start_ms - 15)
        
        # Verifica se há próxima legenda para não sobrepor
        if next_index < len(self.subtitles):
            next_sub_start = self.subtitles[next_index]['start_ms']
            end_ms = min(end_ms + 15, next_sub_start - 1)
        else:
            end_ms = min(end_ms + 15, len(self.audio))

        # Mostra resultado
        matched_text = ' '.join([block['text'] for block in matched_blocks])
        print(f"[Resultado] Texto capturado: '{matched_text}'")
        print(f"[Resultado] Timestamps: {start_ms}ms → {end_ms}ms")
        print(f"[Resultado] Próximo índice: {next_index}")
        print(f"{'='*60}\n")
        
        # Corta e salva áudio
        scene_audio = self.audio[start_ms:end_ms]
        scene_audio.export(output_path, format="mp3")
        
        # Gera arquivo SRT correspondente
        srt_output_path = output_path.rsplit('.', 1)[0] + '.srt'
        self._generate_srt_segment(matched_blocks, start_ms, srt_output_path)
        
        return output_path, srt_output_path

    def segment_all_scenes(self, scenes_data, output_base_dir, method='auto'):
        """
        Segmenta automaticamente todas as cenas do vídeo.
        
        Args:
            scenes_data: Lista de dicionários com dados das cenas
            output_base_dir: Diretório base
            method: Método de matching ('auto', 'window', 'linear')
            
        Returns:
            Dict com informações dos segmentos processados
        """
        segments_info = {}
        
        print(f"\n{'#'*60}")
        print(f"# INICIANDO SEGMENTAÇÃO DE {len(scenes_data)} CENAS")
        print(f"# Método: {method}")
        print(f"{'#'*60}\n")
        
        for i, scene in enumerate(scenes_data):
            scene_id = scene.get("id", f"scene_{i}")
            scene_text = scene.get("narration", {}).get("text", "")
            
            if not scene_text:
                print(f"[AVISO] Cena {scene_id} sem texto para segmentar")
                continue

            # Cria pasta da cena
            scene_output_dir = os.path.join(output_base_dir, scene_id)
            os.makedirs(scene_output_dir, exist_ok=True)
            
            # Define caminhos de saída
            audio_output = os.path.join(scene_output_dir, f"{scene_id}.mp3")
            
            print(f"\n[CENA {i+1}/{len(scenes_data)}] Processando: {scene_id}")
            audio_path, srt_path = self.extract_scene_audio(
                scene_text, 
                audio_output,
                method=method
            )
            
            if audio_path and srt_path:
                segments_info[scene_id] = {
                    "audio_path": audio_path,
                    "srt_path": srt_path,
                    "text": scene_text
                }
                print(f"[CENA {i+1}/{len(scenes_data)}] ✅ Sucesso")
            else:
                print(f"[CENA {i+1}/{len(scenes_data)}] ❌ Falha")
        
        print(f"\n{'#'*60}")
        print(f"# SEGMENTAÇÃO CONCLUÍDA")
        print(f"# Total processado: {len(segments_info)}/{len(scenes_data)} cenas")
        print(f"{'#'*60}\n")
        
        return segments_info