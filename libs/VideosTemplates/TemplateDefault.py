import os

from moviepy.editor import CompositeVideoClip, AudioFileClip, ImageClip, CompositeAudioClip

# from libs.Config import Config
from libs.TTS_Edge import EdgeTTS
from libs.BackgroundVideo import BackgroundVideo
from libs.Subtitle import Subtitle
from libs.Headline import Headline

class TemplateDefault:
    def __init__(self, json_video=None, video_config=None):
        default_json_video = {
            "slug": "default-video",
            "content": {
                "title": "Default Title",
                "description": "Default Description",
                "title_hashtags": "",
                "hashtags": "",
            },
            "headline": False, # pode ter title e subtitle ou False
            "background": {
                "videos_dir": "videos_default/DEFAULT",
                "music_dir": False
            },
            "tts": {
                "narration_text": "This is the default narration text.",
                "edge_tts": {
                    "voice_id": "pt-BR-AntonioNeural",
                    "rate": "+0%",
                }
            },
            "output_ratio": "9:16",
            "youtube": {
                "token_file_name": "token_file_name.json", # canal
                "privacy_status": "private", 
                "publish_at": "0000-00-00 00:00:00"
            }
        }

        # Atualizar o default_json_video com os valores fornecidos em json_video
        default_json_video.update(json_video or {})

        # create self.json_video attribute
        self.json_video = default_json_video        


        default_video_config = {
            "output_folder": "output",
            "project_folder": False,  # será criado depois
            "audio_narration": False,
            "max_total_video_duration": False,
            "subtitles_path": False,
        }

        # Atualizar o default_video_config com os valores fornecidos em video_config
        default_video_config.update(video_config or {})

        # create self.video_config attribute
        self.video_config = default_video_config

        # convert to object attributes
        for k, v in self.json_video.items():
            setattr(self, k, v)
        for k, v in self.video_config.items():
            setattr(self, k, v)

    
    def validate_configs(self):
        # Implement validation logic here
        
        # Criar pasta do projeto usando o slug
        slug = self.video_config.slug
        project_folder = os.path.join(self.video_config.output_folder, slug)
        os.makedirs(project_folder, exist_ok=True)
        print(f"📁 Pasta do projeto: {project_folder}")
        # set indo video_config.project_folder obj attribute
        self.video_config['project_folder'] = project_folder


    def process(self):
        # NARRACAO
        if self.json_video.tts and self.json_video.tts.narration_text:

            narration_text = self.json_video.tts.get("narration_text", False)
            if not narration_text:
                print("⚠️ Nenhum texto de narração encontrado.")
                

            tts = False
            if "edge_tts" in self.json_video.tts:
                # Mudar diretório temporariamente para gerar arquivos na pasta correta
                original_dir = os.getcwd()
                os.chdir(self.video_config.project_folder)

                tts = EdgeTTS(
                    text=narration_text,
                    voice_id=self.json_video.tts.edge_tts.get("voice_id", "pt-BR-AntonioNeural"),
                    output_basename=self.json_video.slug,
                    rate=self.json_video.tts.edge_tts.get("rate", False)
                )
                tts_result = tts.generate_audio_and_subtitles()

                os.chdir(original_dir)

                # set into video_config
                self.video_config.audio_narration = AudioFileClip(os.path.join(self.video_config.project_folder, tts_result['audio_file']))
                self.video_config.max_total_video_duration = self.video_config.audio_narration.duration
                self.video_config.subtitles_path = os.path.join(self.video_config.project_folder, tts_result['subtitle_file'])
                print(f"⏱️  Duração: {self.video_config.max_total_video_duration :.2f}s")

        