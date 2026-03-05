import os
from pathlib import Path

from libs.Whisper.WhisperWorker import WhisperWorker

from libs.Audio.tts.TTS_Edge import EdgeTTS
from libs.Audio.tts.TTS_Polly import PollyTTS
from libs.Audio.tts.TTS_GoogleCloud import GoogleCloudTTS
from libs.Audio.SilenceRemover import SilenceRemover
from libs.Audio.AudioSegmenter import AudioSegmenter

from moviepy.editor import AudioFileClip

class NarrationEngine:
    """
    Gerenciador centralizado para todos os tipos de narração.
    Providers suportados: "edge", "polly", "google", "local_file"
    """
    
    def __init__(self, tts_config, output_base_dir):
        self.tts_config = tts_config
        self.output_base_dir = output_base_dir
        self.provider = tts_config.get("provider", "edge")
        self.segments_processed = {}
        
    def preprocess_scenes(params = {}):
        """
        Pré-processa todas as cenas se for narração local.
        Não usar o self
        """
        defaults = {
            "provider": "local_file",
            "tts_config": {},
            "scenes_data": [],
            "output_base_dir": ""
        }

        for key, value in defaults.items():
            if key not in params:
                params[key] = value
    
        provider = params["provider"]
        tts_config = params["tts_config"]
        scenes_data = params["scenes_data"]
        output_base_dir = params["output_base_dir"]

        if provider != "local_file":
            return scenes_data

        audio_file = tts_config.get("audio_file")
        if not audio_file or not os.path.exists(audio_file):
            raise FileNotFoundError(f"Arquivo de áudio não encontrado: {audio_file}")
        
        print(f"[NarrationEngine] Processando narração local: {audio_file}")
        
        # Usa Whisper para transcrever
        whisper_model = tts_config.get("whisper_model", "base")
        whisper_worker = WhisperWorker(model_size=whisper_model)
        
        # Gera SRT completo
        srt_path = audio_file.replace('.mp3', '.srt').replace('.wav', '.srt')
        whisper_worker.generate_srt(audio_file, srt_path)
        
        # Segmenta por cenas
        segmenter = AudioSegmenter(audio_file, srt_path)
        segments_info = segmenter.segment_all_scenes(scenes_data, output_base_dir)
        
        # Atualiza as cenas com informações dos segmentos
        for scene in scenes_data:
            scene_id = scene.get("id", "")
            if scene_id in segments_info:
                scene["narration"]["audio_file"] = segments_info[scene_id]["audio_path"]
                scene["narration"]["subtitle_file"] = segments_info[scene_id]["srt_path"]

        return scenes_data
        
    def process_scene_narration(self, scene_data, scene_dir):
        """
        Processa narração de uma cena específica.
        
        Returns:
            tuple: (audio_path, duration, subtitle_path)

            scene_dir: Diretório onde os arquivos de áudio e legendas serão salvos.
        """

        if self.provider == "local_file":
            audio_file = scene_data.get("narration", {}).get("audio_file")
            subtitle_file = scene_data.get("narration", {}).get("subtitle_file")

            if not audio_file or not os.path.exists(audio_file):
                print(f"[NarrationEngine] Arquivo de áudio local não encontrado para cena {scene_data.get('id')}: {audio_file}")
                return None, 4.0, None, None

            audio_clip = AudioFileClip(audio_file)
            duration = float(audio_clip.duration or 4.0)

            return audio_clip, duration, subtitle_file

        narration_config = scene_data.get("narration", {})
        text = narration_config.get("text", "")

        if not text:
            print("[NarrationEngine] Cena sem narração. Duração será fixa.")
            return None, narration_config.get("duration", 4.0), None, None

        # Processa com TTS tradicional
        scene_id = scene_data.get('id', 'unknown')
        audio_basename = os.path.join(scene_dir, f"{scene_id}")

        print(f"[NarrationEngine] Gerando áudio para cena {scene_id} com {self.provider}...")

        try:
            if self.provider == "edge":
                return self._process_edge_tts(text, scene_data, audio_basename)
            elif self.provider == "polly":
                return self._process_polly_tts(text, scene_data, audio_basename)
            elif self.provider == "google":
                return self._process_google_tts(text, scene_data, audio_basename)
            else:
                raise ValueError(f"Provider TTS não suportado: {self.provider}")
                
        except Exception as e:
            print(f"[NarrationEngine] ERRO ao processar narração: {e}")
            return None, 4.0, None

    def _process_edge_tts(self, text, scene_data, audio_basename):
        """Processa TTS usando Edge."""
        voice = (scene_data.get("tts", {}).get("voice") or
                 self.tts_config.get("voice") or
                 "pt-BR-AntonioNeural")

        # Rate: cena > global > default "+15%"
        rate = (scene_data.get("tts", {}).get("rate") or
                self.tts_config.get("rate") or
                "+15%")

        # Pitch: cena > global > default "+0Hz"
        pitch = (scene_data.get("tts", {}).get("pitch") or
                 self.tts_config.get("pitch") or
                 "+0Hz")

        tts_params = {
            "text": text,
            "voice_id": voice,
            "output_basename": audio_basename,
            "rate": rate,
            "pitch": pitch,
        }

        tts_engine = EdgeTTS(params=tts_params)
        tts_result = tts_engine.generate_audio_and_subtitles()

        audio_path = tts_result.get("audio_file")
        subtitle_path = tts_result.get("subtitle_file")
        duration = tts_result.get("audio_total_duration", 0)
        word_boundaries = tts_result.get("word_boundaries")

        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Arquivo de áudio não foi criado: {audio_path}")

        audio_clip = AudioFileClip(audio_path)
        duration = float(audio_clip.duration or 4.0)

        return audio_clip, duration, subtitle_path

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

        audio_clip = AudioFileClip(audio_path)
        duration = float(audio_clip.duration or 4.0)

        return audio_clip, duration, subtitle_path

    def _process_google_tts(self, text, scene_data, audio_basename):
        """
        Processa TTS usando Google Cloud TTS (Chirp3-HD, Neural2, WaveNet, Standard).

        Configuração no JSON do canal/vídeo:
        {
            "tts": {
                "provider": "google",
                "credentials_file": "./tokens/credentials.json",  // opcional, usa GOOGLE_APPLICATION_CREDENTIALS se omitido
                "model": "Chirp3-HD",       // Chirp3-HD | Neural2 | WaveNet | Standard
                "voice": "pt-BR-Chirp3-HD-Charon",
                "speaking_rate": 1.15,      // ignorado pelo Chirp3-HD
                "pitch": 0.0,               // ignorado pelo Chirp3-HD
                "volume_gain_db": 0.0
            }
        }

        Override por cena (prioridade maior que o global):
        {
            "tts": {
                "voice": "pt-BR-Chirp3-HD-Aoede",
                "model": "Chirp3-HD"
            }
        }
        """
        # Prioridade: cena > global > defaults
        voice = (scene_data.get("tts", {}).get("voice") or
                 self.tts_config.get("voice") or
                 "pt-BR-Chirp3-HD-Charon")

        model = (scene_data.get("tts", {}).get("model") or
                 self.tts_config.get("model") or
                 "Chirp3-HD")

        # Detecta model automaticamente pela voz se não informado explicitamente
        # ex: "pt-BR-Neural2-A" → Neural2
        if model == "Chirp3-HD" and "Neural2" in voice:
            model = "Neural2"
        elif model == "Chirp3-HD" and "Wavenet" in voice:
            model = "WaveNet"
        elif model == "Chirp3-HD" and "Standard" in voice:
            model = "Standard"

        tts_params = {
            "text":            text,
            "voice_id":        voice,
            "model":           model,
            "output_basename": audio_basename,
            "show_usage_report": False,  # não exibe relatório por cena
        }

        # Credenciais (opcional, fallback para variável de ambiente)
        if "credentials_file" in self.tts_config:
            tts_params["credentials_file"] = self.tts_config["credentials_file"]

        # Parâmetros de voz (ignorados pelo Chirp3-HD, mas válidos para Neural2/WaveNet/Standard)
        if "speaking_rate" in self.tts_config:
            tts_params["speaking_rate"] = float(self.tts_config["speaking_rate"])
        if "pitch" in self.tts_config:
            tts_params["pitch"] = float(self.tts_config["pitch"])
        if "volume_gain_db" in self.tts_config:
            tts_params["volume_gain_db"] = float(self.tts_config["volume_gain_db"])

        # Override por cena
        scene_tts = scene_data.get("tts", {})
        if "speaking_rate" in scene_tts:
            tts_params["speaking_rate"] = float(scene_tts["speaking_rate"])
        if "pitch" in scene_tts:
            tts_params["pitch"] = float(scene_tts["pitch"])

        tts_engine = GoogleCloudTTS(params=tts_params)
        tts_result = tts_engine.generate_audio_and_subtitles()

        audio_path    = tts_result.get("audio_file")
        subtitle_path = tts_result.get("subtitle_file")

        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Arquivo de áudio não foi criado: {audio_path}")

        audio_clip = AudioFileClip(audio_path)
        duration   = float(audio_clip.duration or 4.0)

        return audio_clip, duration, subtitle_path

    def validate_config(self):
        """Valida se a configuração TTS está correta."""
        providers = ["edge", "polly", "google", "local_file"]
        if self.provider not in providers:
            raise ValueError(f"Provider '{self.provider}' não suportado. Use: {providers}")
        
        if self.provider == "local_file":
            audio_file = self.tts_config.get("audio_file")
            if not audio_file:
                raise ValueError("audio_file é obrigatório para provider 'local_file'")
            if not os.path.exists(audio_file):
                raise FileNotFoundError(f"Arquivo de áudio não encontrado: {audio_file}")

        if self.provider == "google":
            creds_file = self.tts_config.get(
                "credentials_file",
                os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
            )
            if not creds_file or not os.path.exists(creds_file):
                raise FileNotFoundError(
                    f"credentials_file não encontrado: '{creds_file}'. "
                    "Defina em tts_config ou via GOOGLE_APPLICATION_CREDENTIALS."
                )
        
        return True
