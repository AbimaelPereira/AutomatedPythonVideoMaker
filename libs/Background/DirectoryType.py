import os
import random
import PIL.Image
from moviepy.editor import VideoFileClip, CompositeVideoClip, concatenate_videoclips
from moviepy.video.fx.all import crop, resize

if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

VALID_EXTENSIONS_VIDEO = ["mp4", "mkv", "avi", "mov", "flv", "webm"]
VALID_EXTENSIONS_IMAGE = ["png", "jpg", "jpeg", "bmp", "gif"]
VALID_EXTENSIONS = VALID_EXTENSIONS_VIDEO + VALID_EXTENSIONS_IMAGE

class DirectoryType:
    def __init__(self, params=None):
        defaults = {
            "path": None,
            "resolution_output": (1080, 1920),
            "valid_extensions": VALID_EXTENSIONS
        }

        # Mesclamos params (se houver)
        if params:
            defaults.update(params)

        # garante que seja uma tupla (width, height)
        ro = defaults.get("resolution_output")
        if isinstance(ro, list):
            defaults["resolution_output"] = tuple(ro)

        for k, v in defaults.items():
            setattr(self, k, v)

    def get_processed_clips(self):
        """
        Lê o diretório e retorna uma lista de clipes já redimensionados e cortados.
        Esta função deve ser chamada apenas uma vez por diretório para alimentar o cache.
        """
        if not self.path or not os.path.exists(self.path):
            print(f"[Aviso] Direitório não encontrado: {self.path}")
            return []

        files = [
            os.path.join(self.path, f) 
            for f in os.listdir(self.path) 
            if f.lower().endswith(tuple(self.valid_extensions))
        ]
        
        if not files:
            raise Exception(f"Nenhum arquivo de mídia encontrado em {self.path}")
        
        clips = []
        for file_path in files:
            # get extension
            extension = os.path.splitext(file_path)[1][1:].lower()

            clip = None
            if extension in VALID_EXTENSIONS_VIDEO:
                clip = self._load_and_resize_video(file_path)
            elif extension in VALID_EXTENSIONS_IMAGE:
                clip = self._load_and_resize_image(file_path)
            
            if clip:
                clips.append(clip)

        return clips

    def _load_and_resize_video(self, file_path):
        try:
            video = VideoFileClip(file_path, audio=False)

            width, height = video.size
            target_w, target_h = self.resolution_output
            original_ratio = width / height
            target_ratio = target_w / target_h

            if original_ratio > target_ratio:
                # video mais largo que o target -> crop horizontalmente
                new_w = int(height * target_ratio)
                x_center = width / 2
                video = crop(video, x1=int(x_center - new_w / 2), x2=int(x_center + new_w / 2), y1=0, y2=height)
            elif original_ratio < target_ratio:
                # video mais alto que o target -> crop verticalmente
                new_h = int(width / target_ratio)
                y_center = height / 2
                video = crop(video, y1=int(y_center - new_h / 2), y2=int(y_center + new_h / 2), x1=0, x2=width)

            resized = resize(video, newsize=(target_w, target_h))
            
            return resized
        except Exception as e:
            print(f"[ERRO DEBUG_BV] Falha em load_and_resize_clip para {file_path}: {e}")
            return None
    
    def _load_and_resize_image(self, file_path):
        try:
            image_clip = PIL.Image.open(file_path)
            width, height = image_clip.size
            target_w, target_h = self.resolution_output
            original_ratio = width / height
            target_ratio = target_w / target_h

            if original_ratio > target_ratio:
                # imagem mais larga que o target -> crop horizontalmente
                new_w = int(height * target_ratio)
                x_center = width / 2
                image_clip = image_clip.crop((int(x_center - new_w / 2), 0, int(x_center + new_w / 2), height))
            elif original_ratio < target_ratio:
                # imagem mais alta que o target -> crop verticalmente
                new_h = int(width / target_ratio)
                y_center = height / 2
                image_clip = image_clip.crop((0, int(y_center - new_h / 2), width, int(y_center + new_h / 2)))

            image_clip = image_clip.resize((target_w, target_h))
            video_clip = ImageClip(image_clip)

            return video_clip
        except Exception as e:
            print(f"[ERRO DEBUG_BV] Falha em _load_and_resize_image para {file_path}: {e}")
            return None
