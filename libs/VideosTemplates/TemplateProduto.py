import os
from libs.TemplateMaster import TemplateMaster
from moviepy.editor import CompositeVideoClip, CompositeAudioClip

SOUND_EFFECTS_PATH = "./assets/sound_effects/"

class TemplateProduto:
    def __init__(self, video_config):
        """
        Inicializa o template com as configurações do vídeo.
        
        Args:
            video_config: Dicionário com todas as configurações do vídeo
        """
        self.video_config = video_config
        self.tm = None

    def validate_configs(self):

    def process(self):
        try:
            slug = self.video_config["slug"]
            output_folder = f"output/{slug}"
            
            print(f"\n🎬 Gerando vídeo: {self.video_config['content']['title'][:50]}...")
            print(f"📐 Proporção: {self.video_config['output_ratio']}")
            
            # Criar pasta de saída
            os.makedirs(output_folder, exist_ok=True)
            print(f"📁 Pasta do projeto: {output_folder}")
            
            # Inicializar TemplateMaster
            self.tm = TemplateMaster({
                "slug": slug,
                "output_folder": output_folder,
                "output_ratio": self.video_config["output_ratio"],
            })
            
            
            
            # 6. Renderização
            output_file = os.path.join(
                output_folder,
                f"{slug}.mp4"
            )
            
            print(f"💾 Renderizando vídeo: {output_file}")
            final.write_videofile(
                output_file,
                codec="libx264",
                audio_codec="aac",
                fps=24,
                threads=5,
                temp_audiofile=os.path.join(output_folder, "temp-audio.m4a"),
                remove_temp=True,
                bitrate="4000k",
                preset="superfast",
            )
            
            print("✅ Vídeo salvo com sucesso!")
            
            # 7. Upload para YouTube (opcional)
            if self.video_config.get("youtube"):
                print("\n📤 Preparando upload para YouTube...")
                
                video_id = self.tm.upload_to_youtube({
                    "video_path": output_file,
                    "content": self.video_config.get("content", {}),
                    "youtube": self.video_config["youtube"],
                    "tts": self.video_config.get("tts", {}),
                    "remove_project_folder": self.video_config["youtube"].get("remove_project_folder", False)
                })
                
                if not video_id:
                    print("⚠️ Upload falhou, mas o vídeo foi salvo localmente.")
                    return False
            
            return True
            
        except Exception as e:
            print(f"\n❌ ERRO ao processar vídeo: {e}")
            import traceback
            traceback.print_exc()
            return False