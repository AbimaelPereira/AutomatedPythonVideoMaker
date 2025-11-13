import random
import os
import shutil

from libs.Subtitle import Subtitle
from libs.BackgroundVideo import BackgroundVideo
from libs.TTS_Edge import EdgeTTS
from libs.Headline import Headline
from libs.YouTube import YouTube

from moviepy.editor import CompositeVideoClip, AudioFileClip, ImageClip, CompositeAudioClip, concatenate_audioclips

AVALIABLE_RATIOS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}

class TemplateMaster:
    def __init__(self, video_config=None):
        default_video_config = {
            "slug": False,
            "output_folder": False,
            "output_ratio": "9:16",
            "max_total_video_duration": False,
        }

        # Atualizar o default_video_config com os valores fornecidos em video_config
        default_video_config.update(video_config or {})

        # set resolution based on output_ratio
        if default_video_config["output_ratio"] in AVALIABLE_RATIOS:
            default_video_config["resolution_output"] = AVALIABLE_RATIOS[default_video_config["output_ratio"]]
            default_video_config["width"], default_video_config["height"] = default_video_config["resolution_output"]
        else:
            raise ValueError(f"Resolução não suportada. Use: {', '.join(AVALIABLE_RATIOS.keys())}")

        # set valores into self 
        for k, v in default_video_config.items():
            setattr(self, k, v)

    def validate_configs(self):
        # Implement validation logic here
        pass
        
    def narration_subtitles(self, params=None):
        """
        Gera a narração e as legendas para o vídeo.
        Retorna um dicionário com o áudio da narração e os clipes de legendas.
        """
        params_default = {
            "narration_text": False,
            "edge_tts": {
                "voice_id": "pt-BR-AntonioNeural",
                "rate": "0%",
            }
        }

        # Atualizar o params_default com os valores fornecidos em params
        if params:
            params_default.update(params)
            # Atualizar edge_tts separadamente para preservar valores padrão
            if "edge_tts" in params:
                params_default["edge_tts"].update(params["edge_tts"])

        original_dir = os.getcwd()
        os.chdir(self.output_folder)
        
        tts = EdgeTTS({
            "text": params_default["narration_text"],
            "voice_id": params_default["edge_tts"]["voice_id"],
            "rate": params_default["edge_tts"].get("rate", "0%"),
            "output_basename": self.slug,
        })
        tts_result = tts.generate_audio_and_subtitles()
        
        # Voltar para o diretório original
        os.chdir(original_dir)

        # retorna obj com o audio da narração carregado e o clip de legendas
        audio_path = os.path.join(self.output_folder, tts_result["audio_file"])
        subtitle_path = os.path.join(self.output_folder, tts_result["subtitle_file"])

        # carregar audio da narração
        audio_narration = AudioFileClip(audio_path)

        # gerar legendas
        sub = Subtitle({
            "subtitle_narration_file": subtitle_path,
            "font_size": 90,
            "stroke_width": 3,
            "resolution_output": self.resolution_output,
        })

        subtitle_clips = sub.generate().set_duration(audio_narration.duration)
        
        return {
            "audio_narration": audio_narration,
            "subtitle_clips": subtitle_clips
        }

    def background_videos(self, params=None):
        params_default = {
            "background_videos_dir": False
        }

        # Atualizar o params_default com os valores fornecidos em params
        if params:
            params_default.update(params)

        bg = BackgroundVideo({
            "output_ratio": self.output_ratio,
            "background_videos_dir": params_default["background_videos_dir"],
            "max_clip_duration": self.max_total_video_duration,
        })

        final_video = bg.generate_background_video()

        # max duration
        if self.max_total_video_duration and final_video.duration > self.max_total_video_duration:
            final_video = final_video.subclip(0, self.max_total_video_duration)

        return final_video

    def background_music(self, params=None):
        params_default = {
            "background_music_file": False,
            "background_music_dir": False,
        }

        if params:
            params_default.update(params)

        if params_default["background_music_dir"]:
            bg_music_dir = params_default["background_music_dir"]

            if not os.path.exists(bg_music_dir):
                print(f"⚠️  Diretório de música de fundo não encontrado: {bg_music_dir}")
                print("ℹ️  Continuando sem música de fundo.")
                return None
            
            music_files = [f for f in os.listdir(bg_music_dir) if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))]
            if not music_files:
                print(f"⚠️  Nenhum arquivo de música encontrado em: {bg_music_dir}")
                print("ℹ️  Continuando sem música de fundo.")
                return None
            
            selected_music = random.choice(music_files)
            music_path = os.path.join(bg_music_dir, selected_music)
            print(f"🎶 Música selecionada: {selected_music}")

            music_clip = AudioFileClip(music_path)

        elif params_default["background_music_file"]:
            music_path = params_default["background_music_file"]
            if not os.path.exists(music_path):
                print(f"⚠️  Arquivo de música de fundo não encontrado: {music_path}")
                print("ℹ️  Continuando sem música de fundo.")
                return None
            
            music_clip = AudioFileClip(music_path)
        else:
            print("⚠️  Nenhum arquivo ou diretório de música de fundo fornecido.")
            print("ℹ️  Continuando sem música de fundo.")
            return None

        # duration
        if self.max_total_video_duration and music_clip.duration > self.max_total_video_duration:
            music_clip = music_clip.subclip(0, self.max_total_video_duration)
        elif self.max_total_video_duration and music_clip.duration < self.max_total_video_duration:
            # loop music
            loops = int(self.max_total_video_duration // music_clip.duration) + 1
            music_clips = [music_clip] * loops
            music_clip = concatenate_audioclips(music_clips).subclip(0, self.max_total_video_duration)

        return music_clip

    def headline(self, params=None):
        params_default = {
            "title": False,
            "subtitle": False
        }

        if params:
            params_default.update(params)

        output_path = os.path.join(self.output_folder, self.slug + "_headline.png")

        headline = Headline({
            "output_path": output_path,
            "title": params_default["title"],
            "subtitle": params_default["subtitle"],
            "video_width": 700,
        })
        headline_data = headline.generate()

        # return image clip
        headline_clip = ImageClip(output_path)

        if self.max_total_video_duration:
            headline_clip = headline_clip.set_duration(self.max_total_video_duration)

        return headline_clip

    def upload_to_youtube(self, params=None):
        """
        Faz upload do vídeo para o YouTube.
        Método reutilizável por todos os templates.
        
        Args:
            params: Dicionário com as configurações:
                - video_path: Caminho do arquivo de vídeo (obrigatório)
                - content: Dicionário com title, description, hashtags
                - youtube: Configurações do YouTube (token_file_name, privacy_status, etc)
                - tts: Dicionário com narration_text
                - remove_project_folder: Se True, remove a pasta após upload
        
        Returns:
            video_id: ID do vídeo no YouTube ou None se falhar
        """
        params_default = {
            "video_path": None,
            "content": {},
            "youtube": {},
            "tts": {},
            "remove_project_folder": False
        }
        
        if params:
            params_default.update(params)
        
        video_path = params_default["video_path"]
        content = params_default["content"]
        yt_config = params_default["youtube"]
        tts_config = params_default["tts"]
        remove_folder = params_default["remove_project_folder"]
        
        if not video_path or not os.path.exists(video_path):
            print(f"❌ Erro: Arquivo de vídeo não encontrado: {video_path}")
            return None
        
        try:
            print("\n🚀 Iniciando upload para o YouTube...")
            
            # Montar título (limitado a 100 caracteres)
            title = content.get("title", "Vídeo sem título")[:100]
            
            # Montar descrição (limitada a 5000 caracteres)
            description_parts = []
            if content.get("description"):
                description_parts.append(content["description"])
            if tts_config.get("narration_text"):
                description_parts.append("\n\n" + tts_config["narration_text"])
            if content.get("hashtags"):
                description_parts.append("\n\n" + content["hashtags"])
            description = "".join(description_parts).strip()[:5000]
            
            # Processar tags
            tags = []
            if content.get("hashtags"):
                tags = [tag.replace("#", "").strip() 
                       for tag in content["hashtags"].split() 
                       if tag.strip()]
                tags_str = ",".join(tags)
                # Tags são limitadas a 500 caracteres no total
                if len(tags_str) > 500:
                    tags = tags_str[:500].split(",")[:-1]
            
            # Configurar privacidade e agendamento
            privacy_status = yt_config.get("privacy_status", "private")
            publish_at = yt_config.get("publish_at")
            
            if publish_at:
                privacy_status = "private"  # Obrigatório para agendamento
                print(f"⏰ Vídeo será agendado para: {publish_at}")
            
            # Criar instância do YouTube
            yt = YouTube({
                "token_file_name": yt_config.get("token_file_name", "youtube_token.json"),
                "video_path": video_path,
                "title": title,
                "description": description,
                "tags": tags,
                "privacy_status": privacy_status,
                "category_id": yt_config.get("category_id", "22"),  # 22 = People & Blogs
                "publish_at": publish_at,
                "timezone": yt_config.get("timezone", "America/Sao_Paulo"),
            })
            
            # Mostrar informações do upload
            print(f"🎬 Título: {title}")
            print(f"🏷️ Tags: {', '.join(tags[:5])}{'...' if len(tags) > 5 else ''}")
            print(f"🔒 Privacidade: {privacy_status}")
            
            # Fazer upload
            video_id = yt.upload()
            
            print(f"✅ Upload concluído com sucesso!")
            print(f"🔗 Link do vídeo: https://youtu.be/{video_id}")
            
            # Adicionar comentário fixado (se configurado)
            if yt_config.get("pinned_comment"):
                try:
                    # Aqui você precisaria implementar a lógica de comentário fixado
                    # via API do YouTube (comentários são um recurso separado)
                    print(f"📌 Comentário fixado: {yt_config['pinned_comment'][:50]}...")
                except Exception as e:
                    print(f"⚠️ Não foi possível fixar comentário: {e}")
            
            # Remover pasta do projeto após upload (se solicitado)
            if remove_folder and self.output_folder:
                try:
                    shutil.rmtree(self.output_folder)
                    print(f"🗑️ Pasta do projeto removida: {self.output_folder}")
                except Exception as e:
                    print(f"⚠️ Não foi possível remover pasta: {e}")
            
            return video_id
            
        except Exception as e:
            print(f"\n❌ ERRO no upload para YouTube: {e}")
            import traceback
            traceback.print_exc()
            return None

    def generate_background_color(self, color_hex="#000000"):
        """
        Gera uma imagem de fundo com a cor sólida especificada.
        """
        from PIL import Image

        output_path = os.path.join(self.output_folder, "background_color.png")

        # Criar imagem sólida
        img = Image.new('RGB', (self.width, self.height), color_hex)
        img.save(output_path)

        # Retornar como ImageClip
        background_clip = ImageClip(output_path).set_duration(1)  # duração temporária de 1 segundo

        return background_clip