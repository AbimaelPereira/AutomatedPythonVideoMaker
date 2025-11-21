import os
import shutil
import subprocess
import numpy as np
import requests  # Import necessário para baixar arquivos
from urllib.parse import urlparse # Import para parsear URLs
from PIL import Image, ImageSequence
from moviepy.editor import VideoFileClip, ImageClip, VideoClip
from moviepy.video.fx.all import crop, resize
from moviepy.video.fx import all as vfx

# Compat Pillow ANTIALIAS
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS


class VisualClip:
    def __init__(self, params=None):
        defaults = {
            "visual_file": None,
            "output_ratio": "9:16",
            "available_resolutions": {"9:16": (1080, 1920), "16:9": (1920, 1080)},
            "resolution_output": (1080, 1920),
            "max_clip_duration": None,
            "default_image_duration": 5,
            "temp_download_path": "./temp_downloads",  # NOVO PARAMETRO
            "valid_video_extensions": ["mp4", "mkv", "avi", "mov", "flv", "webm", "gif"],
            "valid_image_extensions": ["jpg", "jpeg", "png", "bmp", "tiff", "webp"],
        }
        if params:
            defaults.update(params)

        if defaults["output_ratio"] in defaults["available_resolutions"]:
            defaults["resolution_output"] = defaults["available_resolutions"][defaults["output_ratio"]]

        for k, v in defaults.items():
            setattr(self, k, v)

        if not self.visual_file:
            raise ValueError("visual_file é obrigatório")

        # NOVO: Lógica para detectar e baixar URL
        if self._is_url(self.visual_file):
            print(f"[VisualClip] URL detectada. Iniciando download: {self.visual_file}")
            self.visual_file = self._download_from_url(self.visual_file)

        if not os.path.exists(self.visual_file):
            raise FileNotFoundError(f"Arquivo visual não encontrado: {self.visual_file}")

    # ---------------------------
    # NOVO: Verifica se é URL
    # ---------------------------
    def _is_url(self, path):
        return str(path).startswith(('http://', 'https://'))

    # ---------------------------
    # NOVO: Download do arquivo
    # ---------------------------
    def _download_from_url(self, url):
        try:
            # Cria diretório temporário se não existir
            if not os.path.exists(self.temp_download_path):
                os.makedirs(self.temp_download_path)

            # Extrai o nome do arquivo da URL
            parsed_url = urlparse(url)
            filename = os.path.basename(parsed_url.path)
            
            # Fallback se a URL não tiver nome de arquivo claro (ex: .com/)
            if not filename or '.' not in filename:
                filename = f"downloaded_visual_{hash(url)}.jpg" # Assume jpg como fallback ou use header content-type

            local_path = os.path.join(self.temp_download_path, filename)

            # Se o arquivo já existe, podemos pular o download (cache simples)
            # Comente as duas linhas abaixo se quiser forçar o download sempre
            if os.path.exists(local_path):
                print(f"[VisualClip] Arquivo já existe em cache: {local_path}")
                return local_path

            # Headers para evitar bloqueio (User-Agent)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, stream=True)
            response.raise_for_status()

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"[VisualClip] Download concluído: {local_path}")
            return local_path

        except Exception as e:
            raise Exception(f"[ERRO] Falha ao baixar visual da URL {url}: {str(e)}")

    # ---------------------------
    # util: extensão
    # ---------------------------
    def get_file_extension(self):
        return os.path.splitext(self.visual_file)[1][1:].lower()

    # ---------------------------
    # Detectar transparência
    # ---------------------------
    def file_has_transparency(self):
        ext = self.get_file_extension()

        # Imagens estáticas: PNG, WEBP etc
        if ext in ["png", "webp", "tiff"]:
            try:
                img = Image.open(self.visual_file).convert("RGBA")
                alpha = img.split()[-1]
                has_alpha = alpha.getextrema()[0] < 255
                return has_alpha
            except Exception:
                return False

        # GIFs
        if ext == "gif":
            try:
                img = Image.open(self.visual_file)
                if img.info.get("transparency") is not None:
                    return True

                for frame in ImageSequence.Iterator(img):
                    frame = frame.convert("RGBA")
                    alpha = frame.split()[-1]
                    if alpha.getextrema()[0] < 255:
                        return True
                return False
            except Exception:
                return False

        if ext in ["webm", "mov"]:
            return False

        return False

    # ---------------------------
    # Detectar "fundo branco" (color key fallback)
    # ---------------------------
    def appears_to_have_white_background(self, threshold=250, sample_pixels=10):
        try:
            img = Image.open(self.visual_file).convert("RGBA")
            w, h = img.size

            boxes = [
                (0, 0, min(sample_pixels, w), min(sample_pixels, h)),
                (max(0, w - sample_pixels), 0, w, min(sample_pixels, h)),
                (0, max(0, h - sample_pixels), min(sample_pixels, w), h),
                (max(0, w - sample_pixels), max(0, h - sample_pixels), w, h),
            ]

            for box in boxes:
                crop_img = img.crop(box).convert("RGB") # Renomeado para evitar conflito com func crop
                for pixel in crop_img.getdata():
                    if pixel[0] < threshold or pixel[1] < threshold or pixel[2] < threshold:
                        return False
            return True
        except Exception:
            return False

    # ---------------------------
    # Carregar GIF com transparência
    # ---------------------------
    def load_gif_with_transparency(self):
        try:
            print("[VisualClip] Carregando GIF com transparência preservada...")
            
            gif = Image.open(self.visual_file)
            frames = []
            durations = []
            
            for frame in ImageSequence.Iterator(gif):
                frame_rgba = frame.convert("RGBA")
                frames.append(np.array(frame_rgba))
                durations.append(gif.info.get('duration', 100) / 1000.0)
            
            if not frames:
                raise ValueError("GIF não contém frames válidos")
            
            total_duration = sum(durations)
            
            def make_frame(t):
                gif_time = t % total_duration
                cumulative_time = 0
                frame_idx = 0
                
                for i, duration in enumerate(durations):
                    cumulative_time += duration
                    if gif_time < cumulative_time:
                        frame_idx = i
                        break
                return frames[frame_idx][:, :, :3]
            
            clip = VideoClip(make_frame, duration=total_duration)
            clip = clip.set_fps(max(1, int(len(frames) / total_duration)))
            
            def make_mask(t):
                gif_time = t % total_duration
                cumulative_time = 0
                frame_idx = 0
                
                for i, duration in enumerate(durations):
                    cumulative_time += duration
                    if gif_time < cumulative_time:
                        frame_idx = i
                        break
                return frames[frame_idx][:, :, 3] / 255.0
            
            mask_clip = VideoClip(make_mask, duration=total_duration, ismask=True)
            mask_clip = mask_clip.set_fps(clip.fps)
            clip = clip.set_mask(mask_clip)
            
            return clip
            
        except Exception as e:
            print(f"[ERRO] Falha ao carregar GIF com transparência: {e}")
            return None

    # ---------------------------
    # carregar vídeo
    # ---------------------------
    def load_video_clip(self):
        try:
            ext = self.get_file_extension()

            if ext == "gif":
                if self.file_has_transparency():
                    return self.load_gif_with_transparency()
                else:
                    clip = VideoFileClip(self.visual_file)
                    return clip
            
            clip = VideoFileClip(self.visual_file, has_mask=True)

            if getattr(clip, "mask", None) is None and self.appears_to_have_white_background():
                try:
                    clip = clip.fx(vfx.mask_color, color=[255, 255, 255], thr=30)
                except Exception as e:
                    print("[VisualClip] falha ao aplicar mask_color no vídeo:", e)

            return clip

        except Exception as e:
            print(f"[ERRO] Falha ao carregar vídeo {self.visual_file}: {e}")
            return None

    # ---------------------------
    # carregar imagem
    # ---------------------------
    def load_image_clip(self):
        try:
            if self.file_has_transparency():
                clip = ImageClip(self.visual_file, transparent=True).set_duration(self.default_image_duration)
            else:
                clip = ImageClip(self.visual_file).set_duration(self.default_image_duration)
                if self.appears_to_have_white_background():
                    try:
                        clip = clip.fx(vfx.mask_color, color=[255, 255, 255], thr=30)
                    except Exception as e:
                        print("[VisualClip] falha ao aplicar mask_color na imagem:", e)

            return clip
        except Exception as e:
            print(f"[ERRO] Falha ao carregar imagem {self.visual_file}: {e}")
            return None

    # ---------------------------
    # entry point
    # ---------------------------
    def generate_visual_clip(self):
        ext = self.get_file_extension()
        if ext in self.valid_video_extensions:
            return self.load_video_clip()
        elif ext in self.valid_image_extensions:
            return self.load_image_clip()
        else:
            raise ValueError(f"Tipo de arquivo não suportado: .{ext}")