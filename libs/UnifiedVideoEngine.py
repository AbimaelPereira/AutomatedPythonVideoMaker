import os
import random
import shutil
import requests
import numpy as np
from moviepy.editor import *
from PIL import Image

from libs.VisualClip import VisualClip
from libs.TTS_Edge import EdgeTTS
from libs.YouTube import YouTube
from libs.Subtitle import Subtitle
from libs.LayoutEngine import LayoutEngine
from libs.Config import Config # Adicionado

# Helper: Forçar RGB de 3 canais
def force_rgb(im):
    return np.dstack((im, im, im)) if im.ndim == 2 else im

# Helper: Converter Hex para Tupla RGB manualmente
def hex_to_rgb(hex_str):
    hex_str = str(hex_str).lstrip('#')
    try:
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    except:
        return (0, 0, 0)

class UnifiedVideoEngine:
    def __init__(self, video_config):
        self.config = video_config
        self.slug = video_config.get("slug", "video_output")
        self.root_output = "output"
        self.output_folder = os.path.join(self.root_output, self.slug)
        
        # CORREÇÃO: Instanciar o objeto Config
        self.app_config = Config()
        
        ratios = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
        self.output_ratio = video_config.get("output_ratio", "9:16")
        self.resolution = ratios.get(self.output_ratio, (1080, 1920))
        
        # Garantir que o objeto Config tenha as dimensões corretas do vídeo
        self.app_config.set_item("width", self.resolution[0])
        self.app_config.set_item("height", self.resolution[1])

        self.width, self.height = self.resolution
        
        if os.path.exists(self.output_folder):
            try: shutil.rmtree(self.output_folder)
            except: pass
        os.makedirs(self.output_folder, exist_ok=True)

    def process(self):
        try:
            print(f"🚀 Iniciando processamento do projeto: {self.slug}")
            final_clips = []
            scenes = self.config.get("scenes", [])
            
            for i, scene in enumerate(scenes):
                print(f"  🎬 Processando cena {i+1}/{len(scenes)} (ID: {scene.get('id', 'unk')})")
                clip = self._process_scene(scene, i)
                if clip: final_clips.append(clip)
            
            if not final_clips: 
                print("❌ Nenhuma cena gerada.")
                return False

            print("  🔨 Concatenando cenas...")
            final_video = concatenate_videoclips(final_clips, method="compose")
            
            out_path = os.path.join(self.output_folder, f"{self.slug}.mp4")
            print(f"  💾 Renderizando vídeo final em: {out_path}")
            
            # Renderização
            final_video.write_videofile(out_path, fps=30, codec="libx264", audio_codec="aac", threads=4)
            
            if self.config.get("youtube"): self._handle_youtube_upload(out_path)
            return True

        except Exception as e:
            print(f"❌ Erro fatal no engine: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    def _create_debug_overlay(self, duration):
        """
        Cria um clipe de debug temporário para visualizar as margens (padding).
        Retorna um ColorClip semi-transparente que cobre a Área Útil (Caixa Principal).
        """
        # Obter configurações de Padding e Dimensões do objeto app_config
        W, H = self.app_config.width, self.app_config.height
        pad_top = self.app_config.padding_top
        pad_side = self.app_config.padding_side
        pad_bot = self.app_config.padding_bottom 

        inner_w = W - 2 * pad_side
        inner_h = H - pad_top - pad_bot 

        # Cor de debug (ex: amarelo semi-transparente)
        color_rgb = (255, 255, 0) 
        opacity = 0.25

        # Adiciona verificação para garantir que o clipe não tenha dimensões zero ou negativas
        if inner_w <= 0 or inner_h <= 0:
            print(f"  [DEBUG] Área útil inválida para o overlay: W={inner_w}, H={inner_h}. Pulando overlay.")
            return None 

        # 1. Cria um clipe do tamanho da área útil
        inner_box = ColorClip((inner_w, inner_h), color=color_rgb, duration=duration)
        
        # 2. Posiciona o clipe na área delimitada pelo padding
        # A posição (x, y) é o canto superior esquerdo do box
        inner_box = inner_box.set_position((pad_side, pad_top))
        
        # 3. Define a opacidade
        inner_box = inner_box.set_opacity(opacity)
        
        return inner_box

    def _process_scene(self, scene_data, index):
        # --- ORGANIZAÇÃO DE PASTAS ---
        scene_id = scene_data.get("id", f"unk_{index}")
        safe_id = "".join([c if c.isalnum() or c in ('-','_') else '_' for c in scene_id])
        scene_dir_name = f"scene_{index+1:02d}_{safe_id}"
        scene_dir = os.path.join(self.output_folder, scene_dir_name)
        os.makedirs(scene_dir, exist_ok=True)
        # -----------------------------

        narration = scene_data.get("narration", {})
        tts_clip = None
        sub_layer = None
        duration = scene_data.get("duration", 5.0)

        # 1. TTS & Legendas
        if narration.get("text"):
            glob_tts = self.config.get("global_settings", {}).get("tts", {})
            voice = scene_data.get("tts", {}).get("voice") or glob_tts.get("voice", "pt-BR-AntonioNeural")
            
            scene_basename = os.path.join(scene_dir, "narration")
            
            tts = EdgeTTS({
                "text": narration["text"], 
                "voice_id": voice, 
                "output_basename": scene_basename,
                "rate": "0%"
            })
            res = tts.generate_audio_and_subtitles()
            
            if os.path.exists(res["audio_file"]):
                tts_clip = AudioFileClip(os.path.abspath(res["audio_file"]))
                duration = tts_clip.duration
            
            if narration.get("subtitles"):
                try:
                    pad_bottom = getattr(self.app_config, 'padding_bottom', 150)
                    
                    sub = Subtitle({
                        "subtitle_narration_file": os.path.abspath(res["subtitle_file"]),
                        "resolution_output": self.resolution,
                        "font_size": 70
                    })
                    sub_layer = sub.generate()
                except Exception as e: print(f"⚠️ Erro legenda: {e}")

        # --- CÁLCULO DE LAYOUT (STACK) ---
        sub_height = 0
        if sub_layer:
            sub_height = getattr(sub_layer, 'h', 0)

        raw_visuals = scene_data.get("visual_elements", [])
        
        prepared_visuals_for_layout = []
        
        for v in raw_visuals:
            v_copy = v.copy()
            
            # NOVO TRECHO: Injeta o tamanho real para text_box antes do LayoutEngine
            if v_copy.get('type') == 'text_box':
                try:
                    v_copy['original_size'] = VisualClip.calculate_text_box_size(v_copy)
                except Exception as e:
                    print(f"⚠️ Erro ao calcular tamanho do text_box: {e}")
                    v_copy['original_size'] = (1920, 1080) # Fallback 
            
            elif 'original_size' not in v_copy:
                v_copy['original_size'] = (1920, 1080) 
                
            prepared_visuals_for_layout.append(v_copy)
            # FIM DO NOVO TRECHO

        layout_results, (sub_x, sub_y) = LayoutEngine.process_stack_layout(
            prepared_visuals_for_layout, 
            sub_height, 
            self.app_config 
        )

        if sub_layer:
            sub_layer = sub_layer.set_position((sub_x, sub_y))
        # ---------------------------------------------

        # 2. Background
        bg_clip = self._get_background_clip(scene_data, duration, scene_dir)

        # 3. Layers (Visuais)
        layers = [bg_clip]
        
        # NOVO: INJETA O OVERLAY DE DEBUG
        if self.app_config.debug_layout:
            print("  [DEBUG] Injetando overlay para visualização do padding.")
            debug_overlay = self._create_debug_overlay(duration)
            if debug_overlay:
                layers.append(debug_overlay)
        
        for index, v_data in enumerate(raw_visuals):
            if index < len(layout_results):
                calc_data = layout_results[index]
                final_w, final_h = calc_data['final_size']
                final_x, final_y = calc_data['final_position']
                
                if 'layout' not in v_data: v_data['layout'] = {}
                
                # Instancia o clip
                vc = VisualClip({
                    "element_data": v_data, 
                    "resolution_output": self.resolution, 
                    "temp_dir": scene_dir,
                    "duration": duration
                })
                c = vc.generate()
                
                if c:
                    # --- APLICAÇÃO CORRIGIDA DO LAYOUT ---
                    
                    # 1. Checa as dimensões reais do clipe
                    clip_w, clip_h = c.size
                    clip_ratio = clip_w / clip_h
                    target_ratio = final_w / final_h
                    
                    # 2. Redimensiona o clipe para preencher o box (Cover/Crop)
                    if clip_ratio > target_ratio:
                        # O clipe é mais largo que o box (precisa cortar lateralmente)
                        # Redimensiona pela altura para garantir que preencha o box verticalmente
                        c = c.resize(height=final_h)
                        # Recorta para a largura do box, centralizando
                        c = c.crop(x_center=c.w/2, width=final_w)
                    else:
                        # O clipe é mais alto que o box (precisa cortar verticalmente)
                        # Redimensiona pela largura para garantir que preencha o box horizontalmente
                        c = c.resize(width=final_w)
                        # Recorta para a altura do box, centralizando
                        c = c.crop(y_center=c.h/2, height=final_h)

                    # 3. Posiciona o clipe cortado/redimensionado
                    c = c.set_position((final_x, final_y))
                    
                    if c.duration is None: c = c.set_duration(duration)
                    elif c.duration > duration: c = c.set_duration(duration)
                    
                    layers.append(c)

        if sub_layer: layers.append(sub_layer)

        # 4. Composite
        comp = CompositeVideoClip(layers, size=self.resolution).set_duration(duration)
        
        audios = []
        if tts_clip: audios.append(tts_clip)
        
        bg_music = self._get_background_music(scene_data, duration, scene_dir)
        if bg_music: audios.append(bg_music)
        
        if audios: comp = comp.set_audio(CompositeAudioClip(audios))
        return comp

    def _get_background_clip(self, scene_data, duration, scene_dir):
        glob_bg = self.config.get("global_settings", {}).get("background", {}).get("visual", {})
        bg = scene_data.get("background", {}).get("visual", glob_bg)
        
        clip = None
        src = bg.get("source")
        
        if src: src = str(src)

        if bg.get("type") in ["image", "image_dir"]:
            if bg["type"] == "image_dir" and os.path.isdir(src):
                files = [os.path.join(src, f) for f in os.listdir(src) if f.endswith(('.jpg','.png'))]
                if files: src = random.choice(files)
            
            if src and os.path.exists(src):
                try:
                    img = Image.open(src).convert("RGB")
                    tmp = os.path.join(scene_dir, f"bg_image.jpg")
                    img.save(tmp)
                    clip = ImageClip(tmp)
                except: pass

        elif bg.get("type") in ["video", "video_dir"]:
            if bg["type"] == "video_dir" and os.path.isdir(src):
                files = [os.path.join(src, f) for f in os.listdir(src) if f.endswith(('.mp4','.mov'))]
                if files: src = random.choice(files)
            
            if src and os.path.exists(src):
                clip = VideoFileClip(src)
                if clip.duration < duration: clip = vfx.loop(clip, duration=duration)

        if not clip: 
            color_str = src if (bg.get("type")=="color" and src) else "#000000"
            rgb_color = hex_to_rgb(color_str)
            clip = ColorClip(self.resolution, color=rgb_color)

        clip = clip.fl_image(force_rgb)

        if isinstance(clip, (ImageClip, VideoFileClip)) and not isinstance(clip, ColorClip):
            ratio_clip = clip.w / clip.h
            ratio_target = self.width / self.height
            if ratio_clip > ratio_target:
                clip = clip.resize(height=self.height)
                clip = clip.crop(x_center=clip.w/2, width=self.width)
            else:
                clip = clip.resize(width=self.width)
                clip = clip.crop(y_center=clip.h/2, height=self.height)

        return clip.set_duration(duration)

    def _get_background_music(self, scene_data, duration, scene_dir):
        glob_audio = self.config.get("global_settings", {}).get("background", {}).get("audio", {})
        audio = scene_data.get("background", {}).get("audio", glob_audio)
        
        src = audio.get("source")
        if src: src = str(src) 

        if audio.get("type") == "url":
            try:
                local = os.path.join(scene_dir, f"bg_music.mp3")
                if not os.path.exists(local):
                    with open(local, 'wb') as f: f.write(requests.get(src).content)
                src = local
            except: pass
        
        if src and os.path.isdir(src):
            files = [os.path.join(src, f) for f in os.listdir(src) if f.lower().endswith(('.mp3', '.wav', '.aac', '.m4a'))]
            if files: src = random.choice(files)
            else: return None

        if src and os.path.exists(src) and os.path.isfile(src):
            try:
                m = AudioFileClip(src)
                if m.duration < duration: m = afx.audio_loop(m, duration=duration)
                else: m = m.subclip(0, duration)
                return m.volumex(audio.get("volume", 0.1))
            except Exception: pass
        
        return None

    def _handle_youtube_upload(self, video_path):
        yt_cfg = self.config.get("youtube", {})
        try:
            yt = YouTube({
                "token_file_name": yt_cfg.get("token_file_name"),
                "video_path": video_path,
                "title": self.config.get("content", {}).get("title"),
                "description": self.config.get("content", {}).get("description"),
                "privacy_status": yt_cfg.get("privacy_status", "private"),
                "publish_at": yt_cfg.get("publish_at")
            })
            yt.upload()
        except Exception as e: print(f"⚠️ Erro upload: {e}")