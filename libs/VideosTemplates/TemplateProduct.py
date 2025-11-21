import os
import json
from libs.TemplateMaster import TemplateMaster
from moviepy.editor import (
    CompositeVideoClip, CompositeAudioClip, ImageClip, 
    VideoFileClip, AudioFileClip, concatenate_videoclips
)

SOUND_EFFECTS_PATH = "./assets/sound_effects/"
SCENES_LIBRARY_PATH = "./assets/scenes_library.json"


class TemplateProduct:
    def __init__(self, video_config):
        """
        Inicializa o template com as configurações do vídeo.
        
        Args:
            video_config: Dicionário com todas as configurações do vídeo
        """
        self.video_config = video_config
        self.tm = None
        self.scenes_library = self._load_scenes_library()

    def _load_scenes_library(self):
        """Carrega a biblioteca de cenas pré-prontas."""
        if os.path.exists(SCENES_LIBRARY_PATH):
            with open(SCENES_LIBRARY_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def validate_configs(self):
        """
        Valida as configurações necessárias para o template.
        Retorna uma lista de erros encontrados.
        """
        errors = []
        
        # Validações obrigatórias
        if not self.video_config.get("slug"):
            errors.append("'slug' é obrigatório")
            
        if not self.video_config.get("output_ratio"):
            errors.append("'output_ratio' é obrigatório")
            
        if not self.video_config.get("product"):
            errors.append("'product' é obrigatório")
        else:
            product = self.video_config["product"]
            if not product.get("name"):
                errors.append("'product.name' é obrigatório")
            if not product.get("price"):
                errors.append("'product.price' é obrigatório")
            elif not product["price"].get("current"):
                errors.append("'product.price.current' é obrigatório")
                
        if not self.video_config.get("scenes"):
            errors.append("'scenes' é obrigatório e deve conter pelo menos uma cena")
        elif not isinstance(self.video_config["scenes"], list) or len(self.video_config["scenes"]) == 0:
            errors.append("'scenes' deve ser uma lista com pelo menos uma cena")
            
        if not self.video_config.get("content"):
            errors.append("'content' é obrigatório")
        elif not self.video_config["content"].get("title"):
            errors.append("'content.title' é obrigatório")
            
        return errors

    def _process_scene(self, scene_config, scene_index):
        """
        Processa uma cena individual e retorna seus componentes.
        
        Args:
            scene_config: Configuração da cena
            scene_index: Índice da cena (para nomear arquivos)
            
        Returns:
            dict com: video_clip, audio_clip, duration
        """
        # Verificar se é uma cena da biblioteca
        if scene_config.get("use_scene_from_library"):
            library_key = scene_config["use_scene_from_library"]
            if library_key not in self.scenes_library:
                print(f"⚠️  Cena '{library_key}' não encontrada na biblioteca!")
                return None
            
            # Carregar configurações da biblioteca
            scene_config = self.scenes_library[library_key].copy()
            print(f"📚 Usando cena da biblioteca: {library_key}")
        
        

    def process(self):
        """
        Processa o vídeo completo seguindo o template de produto.
        Retorna True se sucesso, False se erro.
        """
        try:
            slug = self.video_config["slug"]
            output_folder = f"output/{slug}"
            
            print(f"\n🎬 Gerando vídeo de produto: {self.video_config['content']['title'][:50]}...")
            print(f"📦 Produto: {self.video_config['product']['name']}")
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

            # Geração do background
            background_video_config = self.video_config.get("background", {})
            background_video = None
            if(background_video_config.get("video_dir")):
                self.tm.max_total_video_duration = 60  # Duração máxima provisória
                background_video = self.tm.background_videos({
                    "background_videos_dir": background_video_config["video_dir"]
                })
            elif(background_video_config.get("color")):
                self.tm.generate_background_color(background_video_config["color"])
                background_video = self.tm.generate_background_color(background_video_config["color"])
                background_video = background_video.set_duration(60)  # Duração máxima provisória
            
            # Processar todas as cenas
            print(f"\n🎬 Processando {len(self.video_config['scenes'])} cenas...")
            scene_clips = []
            
            for i, scene_config in enumerate(self.video_config["scenes"]):
                scene_result = self._process_scene(scene_config, i)
                
                if scene_result:
                    scene_clips.append(scene_result["video_clip"])
                else:
                    print(f"⚠️  Cena {i + 1} pulada devido a erros")
            
            if not scene_clips:
                raise ValueError("Nenhuma cena foi processada com sucesso!")
            
            # Concatenar todas as cenas
            print("\n🎬 Concatenando cenas...")
            final_video = concatenate_videoclips(scene_clips, method="compose")
            
            # Adicionar música de fundo (opcional)
            if self.video_config.get("background", {}).get("music_dir"):
                print("🎵 Adicionando música de fundo...")
                
                self.tm.max_total_video_duration = final_video.duration
                bg_music = self.tm.background_music({
                    "background_music_dir": self.video_config["background"]["music_dir"]
                })
                
                if bg_music:
                    # Mixar música de fundo com o áudio existente
                    bg_music = bg_music.volumex(0.15)
                    
                    if final_video.audio:
                        final_audio = CompositeAudioClip([bg_music, final_video.audio])
                        final_video = final_video.set_audio(final_audio)
                    else:
                        final_video = final_video.set_audio(bg_music)
                    
                    print("🔊 Música de fundo mixada")
            
            # Renderização
            output_file = os.path.join(output_folder, f"{slug}.mp4")
            
            print(f"\n💾 Renderizando vídeo: {output_file}")
            print(f"⏱️  Duração total: {final_video.duration:.2f}s")
            
            final_video.write_videofile(
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
            
            # Upload para YouTube (opcional)
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
                    print("⚠️  Upload falhou, mas o vídeo foi salvo localmente.")
                    return False
            
            return True
            
        except Exception as e:
            print(f"\n❌ ERRO ao processar vídeo: {e}")
            import traceback
            traceback.print_exc()
            return False