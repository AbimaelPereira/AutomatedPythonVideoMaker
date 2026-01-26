import os
from pathlib import Path
from libs.TTS_Edge import EdgeTTS
from libs.TTS_Polly import PollyTTS
from libs.AudioSegmenter import AudioSegmenter
from libs.Whisper.WhisperWorker import WhisperWorker

class NarrationEngine:
    """
    Gerenciador centralizado para todos os tipos de narração.
    """
    
    def __init__(self, tts_config, output_base_dir):
        self.tts_config = tts_config
        self.output_base_dir = output_base_dir
        self.provider = tts_config.get("provider", "edge")
        self.segments_processed = {}
        
    def preprocess_scenes(self, scenes_data):
        """
        Pré-processa todas as cenas se for narração local.
        """
        if self.provider == "local_file":
            return self._preprocess_local_narration(scenes_data)
        return None

    def _preprocess_local_narration(self, scenes_data):
        """Processa narração de arquivo local."""
        audio_file = self.tts_config.get("audio_file")
        if not audio_file or not os.path.exists(audio_file):
            raise FileNotFoundError(f"Arquivo de áudio não encontrado: {audio_file}")
        
        print(f"[NarrationEngine] Processando narração local: {audio_file}")
        
        # Usa Whisper para transcrever
        whisper_model = self.tts_config.get("whisper_model", "base")
        whisper_worker = WhisperWorker(model_size=whisper_model)
        
        # Gera SRT completo
        srt_path = audio_file.replace('.mp3', '.srt').replace('.wav', '.srt')
        whisper_worker.generate_srt(audio_file, srt_path)
        
        # Segmenta por cenas
        segmenter = AudioSegmenter(audio_file, srt_path)
        segments_info = segmenter.segment_all_scenes(scenes_data, self.output_base_dir)
        
        # Atualiza as cenas com informações dos segmentos
        for scene in scenes_data:
            scene_id = scene.get("id")
            if scene_id in segments_info:
                scene["_local_narration"] = segments_info[scene_id]
        
        self.segments_processed = segments_info
        return segments_info

    def process_scene_narration(self, scene_data, target_dir):
        """
        Processa narração de uma cena específica.
        
        Returns:
            tuple: (audio_path, duration, subtitle_path, word_boundaries)
        """
        narration_config = scene_data.get("narration", {})
        text = narration_config.get("text", "")

        if not text:
            print("[NarrationEngine] Cena sem narração. Duração será fixa.")
            return None, narration_config.get("duration", 4.0), None, None

        # Verifica se é narração local pré-processada
        local_narration_data = scene_data.get("_local_narration")
        if local_narration_data:
            print(f"[NarrationEngine] Usando narração local para cena {scene_data.get('id')}")
            return (
                local_narration_data["audio_file"],
                local_narration_data["audio_total_duration"],
                local_narration_data["subtitle_file"],
                None
            )

        # Processa com TTS tradicional
        scene_id = scene_data.get('id', 'unknown')
        audio_basename = os.path.join(target_dir, f"audio_{scene_id}")

        print(f"[NarrationEngine] Gerando áudio para cena {scene_id} com {self.provider}...")

        try:
            if self.provider == "edge":
                return self._process_edge_tts(text, scene_data, audio_basename)
            elif self.provider == "polly":
                return self._process_polly_tts(text, scene_data, audio_basename)
            else:
                raise ValueError(f"Provider TTS não suportado: {self.provider}")
                
        except Exception as e:
            print(f"[NarrationEngine] ERRO ao processar narração: {e}")
            return None, 4.0, None, None

    def _process_edge_tts(self, text, scene_data, audio_basename):
        """Processa TTS usando Edge."""
        voice = (scene_data.get("tts", {}).get("voice") or
                 self.tts_config.get("voice") or
                 "pt-BR-AntonioNeural")

        tts_params = {
            "text": text,
            "voice_id": voice,
            "output_basename": audio_basename,
        }

        tts_engine = EdgeTTS(params=tts_params)
        tts_result = tts_engine.generate_audio_and_subtitles()

        audio_path = tts_result.get("audio_file")
        subtitle_path = tts_result.get("subtitle_file")
        duration = tts_result.get("audio_total_duration", 0)
        word_boundaries = tts_result.get("word_boundaries")

        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Arquivo de áudio não foi criado: {audio_path}")

        return audio_path, duration, subtitle_path, word_boundaries

    def _process_polly_tts(self, text, scene_data, audio_basename):
        """Processa TTS usando AWS Polly."""
        voice = (scene_data.get("tts", {}).get("voice") or
                 self.tts_config.get("voice") or
                 "Camila")

        tts_params = {
            "text": text,
            "voice_id": voice,
            "output_basename": audio_basename,
        }
        
        if "region" in self.tts_config:
            tts_params["region"] = self.tts_config["region"]
        if "engine" in self.tts_config:
            tts_params["engine"] = self.tts_config["engine"]

        tts_engine = PollyTTS(params=tts_params)
        tts_result = tts_engine.generate_audio_and_subtitles()

        audio_path = tts_result.get("audio_file")
        subtitle_path = tts_result.get("subtitle_file")
        duration = tts_result.get("audio_total_duration", 0)

        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Arquivo de áudio não foi criado: {audio_path}")

        return audio_path, duration, subtitle_path, None

    def validate_config(self):
        """Valida se a configuração TTS está correta."""
        providers = ["edge", "polly", "local_file"]
        if self.provider not in providers:
            raise ValueError(f"Provider '{self.provider}' não suportado. Use: {providers}")
        
        if self.provider == "local_file":
            audio_file = self.tts_config.get("audio_file")
            if not audio_file:
                raise ValueError("audio_file é obrigatório para provider 'local_file'")
            if not os.path.exists(audio_file):
                raise FileNotFoundError(f"Arquivo de áudio não encontrado: {audio_file}")
        
        return True