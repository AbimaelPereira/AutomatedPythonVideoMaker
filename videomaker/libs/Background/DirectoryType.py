from typing import Dict, List, Tuple, Optional
import os
import random
from moviepy.editor import VideoFileClip, ImageClip
from moviepy.video.fx.all import crop, resize


class DirectoryType:
    """
    Carrega e redimensiona vídeos/imagens de um diretório, retornando uma lista de clips prontos.
    - Cache por path: clips_cache[dir_path] -> List[VideoClip]
    - Não concatena nem faz loop; apenas prepara os clips
    """
    VIDEO_EXTS = {"mp4", "mkv", "avi", "mov", "flv", "webm"}
    IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "tiff"}

    def __init__(self, resolution_output: Tuple[int, int], clips_cache: Dict[str, List]):
        self.resolution_output = tuple(map(int, resolution_output))
        self.clips_cache = clips_cache

    def _list_files(self, directory: str) -> List[str]:
        files: List[str] = []
        if not os.path.isdir(directory):
            return files
        for root, _, filenames in os.walk(directory):
            for fname in filenames:
                ext = fname.rsplit(".", 1)[-1].lower()
                if ext in self.VIDEO_EXTS or ext in self.IMAGE_EXTS:
                    files.append(os.path.join(root, fname))
        return files

    def _fit_clip(self, clip):
        target_w, target_h = self.resolution_output
        width, height = clip.size
        original_ratio = width / height
        target_ratio = target_w / target_h

        if original_ratio > target_ratio:
            new_w = int(height * target_ratio)
            x_center = width / 2
            clip = crop(clip, x1=int(x_center - new_w / 2), x2=int(x_center + new_w / 2), y1=0, y2=height)
        elif original_ratio < target_ratio:
            new_h = int(width / target_ratio)
            y_center = height / 2
            clip = crop(clip, y1=int(y_center - new_h / 2), y2=int(y_center + new_h / 2), x1=0, x2=width)

        return resize(clip, newsize=(target_w, target_h))

    def _make_clip(self, path: str, max_clip_duration: Optional[float], default_image_duration: float):
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in self.VIDEO_EXTS:
            clip = VideoFileClip(path, audio=False)
            if max_clip_duration and clip.duration > max_clip_duration:
                clip = clip.subclip(0, float(max_clip_duration))
        else:
            dur = float(max_clip_duration) if max_clip_duration else default_image_duration
            clip = ImageClip(path).set_duration(dur)
        return self._fit_clip(clip)

    def load_clips(self, cfg: Dict, scene_duration: float) -> List:
        """
        Retorna lista de clips processados do diretório.
        cfg relevantes:
          - source (str) obrigatório
          - shuffle (bool) opcional (default True)
          - max_clips (int) opcional
          - max_clip_duration (float) opcional
          - image_default_duration (float) opcional (default 4.0)
        """
        source_dir = str(cfg.get("source", "")).strip()
        if not source_dir:
            return []

        if source_dir in self.clips_cache:
            return self.clips_cache[source_dir]

        files = self._list_files(source_dir)
        if not files:
            self.clips_cache[source_dir] = []
            return []

        shuffle = bool(cfg.get("shuffle", True))
        max_clips = cfg.get("max_clips")
        max_clip_duration = cfg.get("max_clip_duration")
        image_default_duration = float(cfg.get("image_default_duration", 4.0))

        candidates = list(files)
        if shuffle:
            random.shuffle(candidates)
        if isinstance(max_clips, int) and max_clips > 0:
            candidates = candidates[:max_clips]

        clips: List = []
        for path in candidates:
            try:
                clip = self._make_clip(path, max_clip_duration, min(image_default_duration, float(scene_duration)))
                clips.append(clip)
            except Exception as e:
                print(f"[DirectoryType] ⚠️ Falha ao carregar {path}: {e}")

        self.clips_cache[source_dir] = clips
        return clips