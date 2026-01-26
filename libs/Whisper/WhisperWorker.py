import whisper
import os
import datetime
import torch

class WhisperWorker:
    def __init__(self, model_size="base", device=None):
        """
        Inicializa o Worker do Whisper.
        
        :param model_size: 'tiny', 'base', 'small', 'medium', 'large'
        :param device: 'cuda' (para GPU NVIDIA) ou 'cpu'. Se None, detecta auto.
        """
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        print(f"[WhisperWorker] Carregando modelo '{model_size}' no dispositivo '{self.device}'...")
        self.model = whisper.load_model(model_size, device=self.device)
        print("[WhisperWorker] Modelo carregado.")

    def _format_timestamp(self, seconds):
        """Converte segundos float para formato SRT (00:00:00,000)"""
        td = datetime.timedelta(seconds=seconds)
        # O timedelta pode ter dias, precisamos lidar apenas com horas
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        millis = int(td.microseconds / 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

    def _regroup_words(self, result_data, max_words_per_line):
        """
        Reagrupa as palavras extraídas pelo Whisper em blocos limitados.
        """
        all_words = []
        
        # O Whisper retorna segmentos grandes. Vamos extrair todas as palavras individuais.
        for segment in result_data["segments"]:
            if "words" in segment:
                all_words.extend(segment["words"])
            else:
                # Fallback caso word_timestamps falhe (não deveria acontecer se configurado)
                pass

        subtitle_blocks = []
        current_block = []
        
        for word_info in all_words:
            current_block.append(word_info)
            
            # Se atingiu o limite de palavras, fecha o bloco
            if len(current_block) >= max_words_per_line:
                subtitle_blocks.append(self._create_block_entry(current_block))
                current_block = []
        
        # Adiciona o restante (se houver)
        if current_block:
            subtitle_blocks.append(self._create_block_entry(current_block))
            
        return subtitle_blocks

    def _create_block_entry(self, word_list):
        """Cria um dicionário com start, end e texto combinado de uma lista de palavras."""
        start_time = word_list[0]['start']
        end_time = word_list[-1]['end']
        text = "".join([w['word'] for w in word_list]).strip()
        return {
            "start": start_time,
            "end": end_time,
            "text": text
        }

    def generate_srt(self, audio_path, output_path=None, max_words_per_line=5):
        """
        Gera o arquivo SRT a partir do áudio.
        
        :param audio_path: Caminho do arquivo de áudio.
        :param output_path: Onde salvar o .srt (se None, salva na mesma pasta do áudio).
        :param max_words_per_line: Quantidade máxima de palavras por legenda.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {audio_path}")

        print(f"[WhisperWorker] Transcrevendo: {audio_path}...")
        
        # word_timestamps=True é CRUCIAL para podermos quebrar as frases onde quisermos
        result = self.model.transcribe(audio_path, word_timestamps=True)
        
        # Processa o reagrupamento
        regrouped_subtitles = self._regroup_words(result, max_words_per_line)
        
        # Define caminho de saída
        if output_path is None:
            output_path = os.path.splitext(audio_path)[0] + ".srt"
            
        # Escreve o arquivo SRT
        print(f"[WhisperWorker] Salvando SRT em: {output_path}")
        with open(output_path, "w", encoding="utf-8") as f:
            for index, block in enumerate(regrouped_subtitles, start=1):
                start_str = self._format_timestamp(block['start'])
                end_str = self._format_timestamp(block['end'])
                
                f.write(f"{index}\n")
                f.write(f"{start_str} --> {end_str}\n")
                f.write(f"{block['text']}\n\n")
                
        return output_path