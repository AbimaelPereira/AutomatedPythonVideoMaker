import os
import random
import logging
import PIL.Image
from moviepy.editor import VideoFileClip, CompositeVideoClip, concatenate_videoclips
from moviepy.video.fx.all import crop, resize

if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

logger = logging.getLogger(__name__)


class BackgroundVideo:
    def __init__(self, params=None):
        defaults = {
            "background_videos_dir": None,
            "resolution_output": (1080, 1920),
            "available_resolutions": {"9:16": (1080, 1920), "16:9": (1920, 1080)},
            "output_ratio": "9:16",
            "max_clip_duration": 4,
            "max_total_video_duration": None,
            "crossfade_duration": 0.8,
            "enable_crossfade": False, 
            "max_clips": None,
            "shuffle_clips": True,
            "valid_extensions": ["mp4", "mkv", "avi", "mov", "flv", "webm"],
            "loop_background": True,
            # Proxy configuration
            "proxy_enabled": True,
            "proxy_cache_dir": "./cache/proxies",
            "proxy_resolution": "1280x720",
            "proxy_bitrate": None,
            "proxy_regen_on_source_change": True,
        }
        if params:
            defaults.update(params)
        if defaults["output_ratio"] in defaults["available_resolutions"]:
            defaults["resolution_output"] = defaults["available_resolutions"][defaults["output_ratio"]]
        for k, v in defaults.items():
            setattr(self, k, v)
        
        # Initialize ProxyCache if enabled
        self.proxy_cache = None
        if self.proxy_enabled:
            try:
                from libs.ProxyCache import ProxyCache
                self.proxy_cache = ProxyCache(
                    cache_dir=self.proxy_cache_dir,
                    resolution=self.proxy_resolution,
                    bitrate=self.proxy_bitrate,
                    regen_on_source_change=self.proxy_regen_on_source_change
                )
                logger.info("ProxyCache initialized for BackgroundVideo")
            except Exception as e:
                logger.warning(f"Failed to initialize ProxyCache: {e}. Proxies disabled.")
                self.proxy_enabled = False

    def load_and_resize_clip(self, video_path):
        try:
            # Use proxy if enabled
            actual_path = video_path
            if self.proxy_enabled and self.proxy_cache:
                try:
                    actual_path = self.proxy_cache.get_or_create(video_path)
                    if actual_path != video_path:
                        logger.info(f"Using proxy for {os.path.basename(video_path)}")
                except Exception as e:
                    logger.warning(f"Failed to get proxy for {video_path}: {e}. Using original.")
                    actual_path = video_path
            else:
                logger.debug(f"Using original file: {os.path.basename(video_path)}")
            
            print(f"[DEBUG_BV: load_and_resize_clip] Loading and resizing: {os.path.basename(actual_path)}")
            video = VideoFileClip(actual_path, audio=False)
            if video.duration > self.max_clip_duration:
                video = video.subclip(0, self.max_clip_duration)

            width, height = video.size
            target_w, target_h = self.resolution_output
            original_ratio = width / height
            target_ratio = target_w / target_h

            if original_ratio > target_ratio:
                new_w = int(height * target_ratio)
                x_center = width / 2
                video = crop(video, x1=int(x_center - new_w / 2), x2=int(x_center + new_w / 2), y1=0, y2=height)
            elif original_ratio < target_ratio:
                new_h = int(width / target_ratio)
                y_center = height / 2
                video = crop(video, y1=int(y_center - new_h / 2), y2=int(y_center + new_h / 2), x1=0, x2=width)

            return resize(video, newsize=(target_w, target_h))
        except Exception as e:
            print(f"[ERRO DEBUG_BV] Falha em load_and_resize_clip para {video_path}: {e}")
            return None

    def apply_crossfade_transition(self, clips):
        if not clips:
            return None
        base = clips[0]
        for next_clip in clips[1:]:
            next_clip = next_clip.crossfadein(self.crossfade_duration).set_start(base.duration - self.crossfade_duration)
            base = CompositeVideoClip([base, next_clip]).set_duration(base.duration + next_clip.duration - self.crossfade_duration)
        return base

    def generate_background_video(self, preloaded_clips=None):
        print("[DEBUG_BV: generate_background_video] INICIADO. Isto deve ser chamado apenas para fundos de vídeo.")

        clips = preloaded_clips if preloaded_clips is not None else self.get_processed_clips()

        if not clips:
            return None

        # IMPORTANTE: Use uma cópia da lista para o shuffle não afetar o cache original
        working_clips = list(clips)
        if self.shuffle_clips:
            random.shuffle(working_clips)
        if self.max_clips:
            working_clips = working_clips[:self.max_clips]

        if not working_clips:
            print("[ERRO] Nenhum clipe pôde ser carregado.")
            return None

        if self.max_total_video_duration:
            final_duration = 0
            extended_clips = []
            idx = 0
            while True:
                clip = working_clips[idx % len(working_clips)]
                if extended_clips:
                    nova_duracao = final_duration + clip.duration - self.crossfade_duration
                else:
                    nova_duracao = final_duration + clip.duration

                if nova_duracao >= self.max_total_video_duration:
                    restante = self.max_total_video_duration - final_duration
                    if extended_clips:
                        restante += self.crossfade_duration
                    if restante < clip.duration:
                        clip = clip.subclip(0, restante)
                    extended_clips.append(clip)
                    break
                else:
                    extended_clips.append(clip)
                    final_duration = nova_duracao
                    idx += 1
            working_clips = extended_clips
        elif self.loop_background:
            working_clips = working_clips * 3

        if self.enable_crossfade:
            final_video = self.apply_crossfade_transition(working_clips)
        else:
            final_video = concatenate_videoclips(working_clips, method='compose')

        if self.max_total_video_duration:
            final_video = final_video.subclip(0, self.max_total_video_duration)
        
        print("[DEBUG_BV: generate_background_video] FINALIZADO.")
        return final_video

    def get_processed_clips(self):
        """
        Lê o diretório e retorna uma lista de clipes já redimensionados e cortados.
        Esta função deve ser chamada apenas uma vez por diretório para alimentar o cache.
        """
        if not self.background_videos_dir or not os.path.exists(self.background_videos_dir):
            print(f"[Aviso] Direitório não encontrado: {self.background_videos_dir}")
            return []
            
        video_files = [f for f in os.listdir(self.background_videos_dir)
                    if any(f.lower().endswith(ext) for ext in self.valid_extensions)]
        
        clips = []
        for video_name in video_files:
            path = os.path.join(self.background_videos_dir, video_name)
            clip = self.load_and_resize_clip(path)
            if clip:
                clips.append(clip)
        return clips