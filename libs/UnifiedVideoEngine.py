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
        
        ratios = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
        self.output_ratio = video_config.get("output_ratio", "9:16")
        self.resolution = ratios.get(self.output_ratio, (1080, 1920))
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

    def _process_scene(self, scene_data, index):
        # --- ORGANIZAÇÃO DE PASTAS ---
        # Cria uma pasta específica para esta cena (ex: scene_01_intro)
        scene_id = scene_data.get("id", f"unk_{index}")
        # Sanitiza o nome da pasta
        safe_id = "".join([c if c.isalnum() or c in ('-','_') else '_' for c in scene_id])
        scene_dir_name = f"scene_{index+1:02d}_{safe_id}"
        scene_dir = os.path.join(self.output_folder, scene_dir_name)
        os.makedirs(scene_dir, exist_ok=True)
        # -----------------------------

        narration = scene_data.get("narration", {})
        tts_clip = None
        sub_layer = None
        duration = scene_data.get("duration", 5.0)

        # 1. TTS
        if narration.get("text"):
            glob_tts = self.config.get("global_settings", {}).get("tts", {})
            voice = scene_data.get("tts", {}).get("voice") or glob_tts.get("voice", "pt-BR-AntonioNeural")
            
            # Salva o áudio dentro da pasta da cena
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
                    sub = Subtitle({
                        "subtitle_narration_file": os.path.abspath(res["subtitle_file"]),
                        "resolution_output": self.resolution,
                        "font_size": 70
                    })
                    sub_layer = sub.generate()
                except Exception as e: print(f"⚠️ Erro legenda: {e}")

        # 2. Background (Passamos scene_dir para salvar assets lá)
        bg_clip = self._get_background_clip(scene_data, duration, scene_dir)

        # 3. Layers
        layers = [bg_clip]
        for v in scene_data.get("visual_elements", []):
            vc = VisualClip({
                "element_data": v, 
                "resolution_output": self.resolution, 
                "temp_dir": scene_dir, # Assets visuais salvos na pasta da cena
                "duration": duration
            })
            c = vc.generate()
            if c: 
                # Ajuste de duração
                if c.duration is None: c = c.set_duration(duration)
                elif c.duration > duration: c = c.set_duration(duration)
                layers.append(c)

        if sub_layer: layers.append(sub_layer)

        # 4. Composite
        comp = CompositeVideoClip(layers, size=self.resolution).set_duration(duration)
        
        audios = []
        if tts_clip: audios.append(tts_clip)
        
        # Música de fundo (Passamos scene_dir)
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
                    # Salva cópia temporária na pasta da cena
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

        # Fallback e ColorClip
        if not clip: 
            color_str = src if (bg.get("type")=="color" and src) else "#000000"
            rgb_color = hex_to_rgb(color_str)
            clip = ColorClip(self.resolution, color=rgb_color)

        # Force RGB
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
                # Baixa música para a pasta da cena
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