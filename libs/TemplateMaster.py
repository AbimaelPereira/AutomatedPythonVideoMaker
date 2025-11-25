import random
import os
import shutil
import requests # Novo import
from rembg import remove # Novo import
from PIL import Image # Novo import
import io # Novo import

from libs.Subtitle import Subtitle
from libs.BackgroundVideo import BackgroundVideo
from libs.TTS_Edge import EdgeTTS
from libs.Headline import Headline
from libs.YouTube import YouTube
from libs.VisualClip import VisualClip

from moviepy.editor import CompositeVideoClip, AudioFileClip, ImageClip, CompositeAudioClip, concatenate_audioclips

AVALIABLE_RATIOS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}

class TemplateMaster:
    def __init__(self, video_config=None):
        # ... (mantenha o __init__ igual ao original)
        default_video_config = {
            "slug": False,
            "output_folder": False,
            "output_ratio": "9:16",
            "max_total_video_duration": False,
        }

        default_video_config.update(video_config or {})

        if default_video_config["output_ratio"] in AVALIABLE_RATIOS:
            default_video_config["resolution_output"] = AVALIABLE_RATIOS[default_video_config["output_ratio"]]
            default_video_config["width"], default_video_config["height"] = default_video_config["resolution_output"]
        else:
            raise ValueError(f"Resolução não suportada. Use: {', '.join(AVALIABLE_RATIOS.keys())}")

        for k, v in default_video_config.items():
            setattr(self, k, v)

    # ... (mantenha validate_configs e narration_subtitles iguais)
    def validate_configs(self):
        pass

    def narration_subtitles(self, params=None):
        # ... (código existente de narration_subtitles) ...
        params_default = {
            "narration_text": False,
            "edge_tts": {
                "voice_id": "pt-BR-AntonioNeural",
                "rate": "0%",
            },
            "output_folder": self.output_folder,
            "output_basename": self.slug,
        }

        if params:
            params_default.update(params)
            if "edge_tts" in params:
                params_default["edge_tts"].update(params["edge_tts"])

        print(params_default)

        original_dir = os.getcwd()
        os.chdir(params_default["output_folder"])
        
        tts = EdgeTTS({
            "text": params_default["narration_text"],
            "voice_id": params_default["edge_tts"]["voice_id"],
            "rate": params_default["edge_tts"].get("rate", "0%"),
            "output_basename": params_default["output_basename"],
        })
        tts_result = tts.generate_audio_and_subtitles()
        
        os.chdir(original_dir)

        audio_path = os.path.join(params_default["output_folder"], tts_result["audio_file"])
        subtitle_path = os.path.join(params_default["output_folder"], tts_result["subtitle_file"])

        audio_narration = self.load_audio_clip(audio_path)
        subtitle_clips = self.load_subtitle_clip(subtitle_path).set_duration(audio_narration.duration)
        
        return {
            "audio_narration": audio_narration,
            "subtitle_clips": subtitle_clips
        }

    def load_audio_clip(self, audio_file):
        # ... (código existente) ...
        if not os.path.exists(audio_file):
            raise FileNotFoundError(f"Arquivo de narração não encontrado: {audio_file}")
        
        audio_narration = AudioFileClip(audio_file)
        return audio_narration

    def load_subtitle_clip(self, subtitle_file):
        # ... (código existente) ...
        if not os.path.exists(subtitle_file):
            raise FileNotFoundError(f"Arquivo de legendas não encontrado: {subtitle_file}")
        
        sub = Subtitle({
            "subtitle_narration_file": subtitle_file,
            "font_size": 90,
            "stroke_width": 3,
            "resolution_output": self.resolution_output,
        })

        subtitle_clips = sub.generate()
        return subtitle_clips

    # --- AQUI ESTÁ A MUDANÇA PRINCIPAL ---
    def load_visual_clip(self, visual_file, remove_bg=False):
        """
        Carrega o arquivo visual. 
        Se remove_bg=True, baixa a imagem (se for URL), remove o fundo e salva como PNG.
        """
        final_visual_path = visual_file

        if remove_bg:
            print("  ✨ Removendo fundo da imagem...")
            try:
                input_image = None
                
                # 1. Obter a imagem (URL ou Local)
                if visual_file.startswith(("http:", "https:")):
                    response = requests.get(visual_file)
                    response.raise_for_status()
                    input_image = Image.open(io.BytesIO(response.content))
                    print(f"  ✅ Imagem baixada para remoção de fundo.")
                else:
                    if os.path.exists(visual_file):
                        input_image = Image.open(visual_file)
                    else:
                        print(f"❌ Arquivo não encontrado para remover fundo: {visual_file}")

                if input_image:
                    # 2. Remover fundo usando rembg
                    output_image = remove(input_image)
                    
                    # 3. Salvar imagem processada na pasta de output
                    # Nome do arquivo baseado no original ou hash simples
                    filename = os.path.basename(visual_file).split('?')[0]
                    if not filename or len(filename) > 20: filename = "visual_img.jpg"
                    name_without_ext = os.path.splitext(filename)[0]
                    
                    new_filename = f"{name_without_ext}_no_bg.png"
                    final_visual_path = os.path.join(self.output_folder, new_filename)
                    
                    output_image.save(final_visual_path)
                    print(f"  ✅ Fundo removido: {new_filename}")

            except Exception as e:
                print(f"⚠️ Falha ao remover fundo: {e}. Usando imagem original.")
                final_visual_path = visual_file

        # Passa o caminho (original ou modificado) para o VisualClip
        visual = VisualClip({
            "visual_file": final_visual_path,
            "resolution_output": self.resolution_output,
        })

        visual_clip = visual.generate_visual_clip()
        return visual_clip

    # ... (mantenha background_videos, background_music, headline, upload_to_youtube, generate_background_color iguais) ...
    def background_videos(self, params=None):
        # ... (igual ao original)
        params_default = {
            "background_videos_dir": False
        }
        if params:
            params_default.update(params)

        bg = BackgroundVideo({
            "output_ratio": self.output_ratio,
            "background_videos_dir": params_default["background_videos_dir"],
            "max_clip_duration": self.max_total_video_duration,
        })

        final_video = bg.generate_background_video()

        if self.max_total_video_duration and final_video.duration > self.max_total_video_duration:
            final_video = final_video.subclip(0, self.max_total_video_duration)

        return final_video

    def background_music(self, params=None):
        # ... (igual ao original)
        params_default = {
            "background_music_file": False,
            "background_music_dir": False,
        }

        if params:
            params_default.update(params)

        if params_default["background_music_dir"]:
            bg_music_dir = params_default["background_music_dir"]
            if not os.path.exists(bg_music_dir):
                return None
            music_files = [f for f in os.listdir(bg_music_dir) if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))]
            if not music_files:
                return None
            selected_music = random.choice(music_files)
            music_path = os.path.join(bg_music_dir, selected_music)
            music_clip = AudioFileClip(music_path)
        elif params_default["background_music_file"]:
            music_path = params_default["background_music_file"]
            if not os.path.exists(music_path):
                return None
            music_clip = AudioFileClip(music_path)
        else:
            return None

        if self.max_total_video_duration and music_clip.duration > self.max_total_video_duration:
            music_clip = music_clip.subclip(0, self.max_total_video_duration)
        elif self.max_total_video_duration and music_clip.duration < self.max_total_video_duration:
            loops = int(self.max_total_video_duration // music_clip.duration) + 1
            music_clips = [music_clip] * loops
            music_clip = concatenate_audioclips(music_clips).subclip(0, self.max_total_video_duration)

        return music_clip

    def headline(self, params=None):
        # ... (igual ao original)
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
        headline.generate()
        headline_clip = ImageClip(output_path)
        if self.max_total_video_duration:
            headline_clip = headline_clip.set_duration(self.max_total_video_duration)
        return headline_clip

    def upload_to_youtube(self, params=None):
        """
        Faz upload do vídeo para o YouTube.
        Aceita parâmetros diretos (title, description) ou extrai de 'content'.
        """
        params_default = {
            "video_path": None,
            "content": {},
            "youtube": {},
            "tts": {},
            "remove_project_folder": False,
            # Campos opcionais para override direto
            "title": None,
            "description": None,
            "tags": None
        }
        
        if params:
            params_default.update(params)
        
        video_path = params_default["video_path"]
        content = params_default["content"]
        yt_config = params_default["youtube"]
        tts_config = params_default["tts"]
        
        if not video_path or not os.path.exists(video_path):
            print(f"❌ Erro: Arquivo de vídeo não encontrado: {video_path}")
            return None
        
        try:
            print("\n🚀 Iniciando upload para o YouTube...")
            
            # 1. Definição do Título
            # Usa o passado explicitamente OU pega do content OU usa default
            title = params_default.get("title")
            if not title:
                title = content.get("title", "Vídeo sem título")
            title = title[:100] # Limite do YouTube
            
            # 2. Definição da Descrição
            description = params_default.get("description")
            if not description:
                # Lógica de construção automática (Fallback)
                description_parts = []
                if content.get("description"):
                    description_parts.append(content["description"])
                if tts_config.get("narration_text"):
                    description_parts.append("\n\n" + tts_config["narration_text"])
                if content.get("hashtags"):
                    # Verifica se é lista ou string antes de adicionar
                    tags_text = content["hashtags"]
                    if isinstance(tags_text, list):
                        tags_text = " ".join(tags_text)
                    description_parts.append("\n\n" + str(tags_text))
                description = "".join(description_parts)
            
            description = description.strip()[:5000] # Limite do YouTube
            
            # 3. Definição das Tags
            tags = params_default.get("tags")
            if tags is None:
                # Tenta extrair de hashtags se não foi passado explicitamente
                raw_tags = content.get("hashtags", [])
                if isinstance(raw_tags, str):
                    # Remove # e divide por espaços ou vírgulas
                    tags = [tag.replace("#", "").strip() for tag in raw_tags.replace(",", " ").split() if tag.strip()]
                elif isinstance(raw_tags, list):
                    tags = [str(tag).replace("#", "").strip() for tag in raw_tags]
                else:
                    tags = []
            
            # 4. Configurações Finais
            privacy_status = yt_config.get("privacy_status", "private")
            publish_at = yt_config.get("publish_at")
            
            if publish_at:
                privacy_status = "private"
                print(f"⏰ Vídeo será agendado para: {publish_at}")
            
            # Instancia a classe YouTube com os dados processados
            yt = YouTube({
                "token_file_name": yt_config.get("token_file_name", "youtube_token.json"),
                "video_path": video_path,
                "title": title,
                "description": description,
                "tags": tags,
                "privacy_status": privacy_status,
                "category_id": yt_config.get("category_id", "22"),
                "publish_at": publish_at,
                "timezone": yt_config.get("timezone", "America/Sao_Paulo"),
                "pinned_comment": yt_config.get("pinned_comment")
            })
            
            print(f"🎬 Título: {title}")
            print(f"🔒 Privacidade: {privacy_status}")
            
            video_id = yt.upload()
            
            print(f"✅ Upload concluído com sucesso: https://youtu.be/{video_id}")
            
            # Limpeza
            if params_default["remove_project_folder"] and self.output_folder:
                try:
                    shutil.rmtree(self.output_folder)
                    print(f"🗑️ Pasta do projeto removida.")
                except Exception as e:
                    print(f"⚠️ Erro ao remover pasta: {e}")
            
            return video_id
            
        except Exception as e:
            print(f"\n❌ ERRO no upload para YouTube: {e}")
            import traceback
            traceback.print_exc()
            return None

    def generate_background_color(self, color_hex="#000000"):
        # ... (igual ao original)
        from PIL import Image
        output_path = os.path.join(self.output_folder, "background_color.png")
        img = Image.new('RGB', (self.width, self.height), color_hex)
        img.save(output_path)
        background_clip = ImageClip(output_path).set_duration(1)
        return background_clip