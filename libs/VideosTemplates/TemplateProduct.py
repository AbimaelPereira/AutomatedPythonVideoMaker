import os
import json
from libs.TemplateMaster import TemplateMaster
from moviepy.editor import (
    CompositeVideoClip, CompositeAudioClip, concatenate_videoclips
)

# Constantes baseadas no a.py
ASSETS_DIR = "./assets"
SOUND_EFFECTS_PATH = os.path.join(ASSETS_DIR, "/sound_effects/")

class TemplateProduct:
    def __init__(self, video_config):
        """
        Inicializa o template com as configurações do vídeo.
        """
        self.video_config = video_config
        self.tm = None
        self.background_clip = None # Armazenará o clipe de fundo

    def validate_configs(self):
        """
        Valida as configurações necessárias para o template.
        """
        errors = []
        
        # Validações obrigatórias
        if not self.video_config.get("slug"):
            errors.append("'slug' é obrigatório")
            
        if not self.video_config.get("output_ratio"):
            errors.append("'output_ratio' é obrigatório")
            
        if not self.video_config.get("scenes"):
            errors.append("'scenes' é obrigatório e deve conter pelo menos uma cena")
            
        return errors

    def _process_scene(self, scene_config, scene_index):
        """
        Processa uma cena individual aplicando a lógica do a.py.
        """
        GAP = 250 # Distância entre elementos visuais

        # path of scene
        scene_path = os.path.join(self.tm.output_folder, f"scene_{scene_index+1}")
        os.makedirs(scene_path, exist_ok=True)
        
        audio_narration = None
        audio_sound_effect = None
        subtitle_clips = None
        visual_clip = None

        scene_data = scene_config
        
        # Configuração de TTS e Legendas
        if scene_data.get("narration_text"):
            narration_config = self.video_config.get("tts", {}).copy()
            narration_config["narration_text"] = scene_data["narration_text"]
            narration_config["output_folder"] = scene_path
            narration_config["output_basename"] = f"scene_{scene_index+1}"
            
            # Gera audio e legenda
            audio_and_subtitles = self.tm.narration_subtitles(narration_config)
            audio_narration = audio_and_subtitles["audio_narration"]

            if scene_data.get("subtitle"):
                subtitle_clips = audio_and_subtitles["subtitle_clips"]
        
        # Efeito sonoro
        if scene_data.get("sound_effect"):
            sound_effect_file = os.path.join(SOUND_EFFECTS_PATH, scene_data["sound_effect"])
            if os.path.exists(sound_effect_file):
                audio_sound_effect = self.tm.load_audio_clip(sound_effect_file)

        # Visual (Imagem ou Link)
        if scene_data.get("visual"):
            # AQUI: Passando remove_bg
            should_remove_bg = scene_data.get("remove_bg", False)
            visual_item = scene_data["visual"]

            if not visual_item.startswith(("http:", "https:")):
                visual_item = ASSETS_DIR + visual_item
            
            visual_clip = self.tm.load_visual_clip(
                visual_item,
                remove_bg=should_remove_bg
            )

            width_percent = 1
            if scene_data.get("visual_width_percent"):
                width_percent = scene_data["visual_width_percent"]
            
            # Redimensionar para a largura especificada (padrão para produtos com fundo removido fica ótimo)
            target_width = int(self.tm.width * width_percent)
            visual_clip = visual_clip.resize(width=target_width)

        # --- MONTAGEM DA CENA (COMPOSITING) ---
        
        final_video_scene = None

        # Calcular posições (baseado na lógica do a.py)
        if visual_clip and subtitle_clips:
            # Visual centralizado verticalmente considerando a legenda e o GAP
            visual_y = (self.tm.height - (visual_clip.h + subtitle_clips.h + GAP)) // 2
            subtitle_y = visual_y + visual_clip.h + GAP

            final_video_scene = CompositeVideoClip([
                visual_clip.set_position(("center", visual_y)),
                subtitle_clips.set_position(("center", subtitle_y))
            ], size=(self.tm.width, self.tm.height))

        elif visual_clip:
            # Apenas visual centralizado
            visual_y = (self.tm.height - visual_clip.h) // 2
            final_video_scene = visual_clip.set_position(("center", visual_y))
            # Se for imagem, precisa de duração. Se não tiver audio definindo duração, usa padrão.
            if not audio_narration and not audio_sound_effect:
                 final_video_scene = final_video_scene.set_duration(3) 

        elif subtitle_clips:
            # Apenas legenda centralizada
            subtitle_y = (self.tm.height - subtitle_clips.h) // 2
            final_video_scene = subtitle_clips.set_position(("center", subtitle_y))
        
        # Se nenhum visual foi gerado, mas tem áudio, cria um clipe vazio/transparente
        if not final_video_scene and (audio_narration or audio_sound_effect):
             from moviepy.editor import ColorClip
             duration = 0
             if audio_narration: duration = max(duration, audio_narration.duration)
             if audio_sound_effect: duration = max(duration, audio_sound_effect.duration)
             final_video_scene = ColorClip(size=(self.tm.width, self.tm.height), color=(0,0,0), duration=duration).set_opacity(0)

        # Mixagem de Áudio
        final_audio_scene = None
        if audio_narration and audio_sound_effect:
            final_audio_scene = CompositeAudioClip([audio_sound_effect, audio_narration])
        elif audio_narration:
            final_audio_scene = audio_narration
        elif audio_sound_effect:
            final_audio_scene = audio_sound_effect
        
        if final_video_scene:
            # Definir áudio da cena
            if final_audio_scene:
                final_video_scene = final_video_scene.set_audio(final_audio_scene)
                final_video_scene = final_video_scene.set_duration(final_audio_scene.duration)
            
            # Adicionar Background (se existir)
            if self.background_clip:
                bg = self.background_clip.set_duration(final_video_scene.duration)
                final_video_scene = CompositeVideoClip([bg, final_video_scene], size=(self.tm.width, self.tm.height))
                
            return final_video_scene
            
        return None

    def process(self):
        """
        Processa o vídeo completo.
        """
        try:
            slug = self.video_config["slug"]
            output_folder = f"output/{slug}"
            
            print(f"\n🎬 Gerando vídeo de produto: {self.video_config['content']['title'][:50]}...")
            
            # Criar pasta de saída
            os.makedirs(output_folder, exist_ok=True)
            
            # Inicializar TemplateMaster
            self.tm = TemplateMaster({
                "slug": slug,
                "output_folder": output_folder,
                "output_ratio": self.video_config["output_ratio"],
            })

            # 1. Preparar Background (Color ou Video)
            background_config = self.video_config.get("background", {})
            
            if background_config.get("color"):
                # Gera um clipe de cor sólida para ser reutilizado em cada cena
                print(f"🎨 Gerando background sólido: {background_config['color']}")
                self.background_clip = self.tm.generate_background_color(background_config["color"])
            
            elif background_config.get("video_dir"):
                # Nota: Background animado global é complexo com cenas de durações variáveis.
                # Aqui, usamos a lógica do TemplateMaster para gerar um vídeo longo de fundo
                print("🎥 Gerando background de vídeo...")
                self.tm.max_total_video_duration = 300 # Limite de segurança
                bg_video = self.tm.background_videos({
                    "background_videos_dir": background_config["video_dir"]
                })
                self.background_clip = bg_video

            # 2. Processar todas as cenas
            print(f"\n🎬 Processando {len(self.video_config['scenes'])} cenas...")
            scene_clips = []
            
            for i, scene_config in enumerate(self.video_config["scenes"]):
                try:
                    scene_clip = self._process_scene(scene_config, i)
                    if scene_clip:
                        scene_clips.append(scene_clip)
                    else:
                        print(f"⚠️  Aviso: Cena {i+1} não retornou conteúdo e foi pulada.")
                except Exception as e:
                    print(f"❌ Erro na cena {i+1}: {str(e)}")
                    import traceback
                    traceback.print_exc()
            
            if not scene_clips:
                raise ValueError("Nenhuma cena foi processada com sucesso!")
            
            # 3. Concatenar
            print("\n🎬 Concatenando cenas...")
            final_video = concatenate_videoclips(scene_clips, method="compose")
            
            # 4. Música de Fundo (Opcional)
            if self.video_config.get("background", {}).get("music_dir"):
                print("🎵 Adicionando música de fundo...")
                self.tm.max_total_video_duration = final_video.duration
                bg_music = self.tm.background_music({
                    "background_music_dir": self.video_config["background"]["music_dir"]
                })
                
                if bg_music:
                    bg_music = bg_music.volumex(0.15) # Volume baixo
                    if final_video.audio:
                        final_audio = CompositeAudioClip([final_video.audio, bg_music])
                        final_video = final_video.set_audio(final_audio)
                    else:
                        final_video = final_video.set_audio(bg_music)
            
            # 5. Renderização
            output_file = os.path.join(output_folder, f"{slug}.mp4")
            print(f"\n💾 Renderizando vídeo: {output_file}")
            
            final_video.write_videofile(
                output_file,
                codec="libx264",
                audio_codec="aac",
                fps=24,
                threads=4,
                temp_audiofile=os.path.join(output_folder, "temp-audio.m4a"),
                remove_temp=True,
                bitrate="4000k",
                preset="superfast", # Use 'medium' para melhor qualidade
            )
            
            print("✅ Vídeo salvo com sucesso!")
            
            # 6. Upload para YouTube (opcional)
            # Esta parte NÃO precisa ser alterada, pois usa apenas 'content' e 'youtube'
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
            print(f"\n❌ ERRO FATAL ao processar vídeo: {e}")
            import traceback
            traceback.print_exc()
            return False