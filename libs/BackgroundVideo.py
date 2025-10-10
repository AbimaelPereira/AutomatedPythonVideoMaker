import os
import random
import PIL.Image
from moviepy.editor import VideoFileClip, CompositeVideoClip, concatenate_videoclips
from moviepy.video.fx.all import crop, resize

if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS


class BackgroundVideo:
    def __init__(self, params=None):
        defaults = {
            "background_videos_dir": None,
            "resolution_output": (1080, 1920),
            "available_resolutions": {"9:16": (1080, 1920), "16:9": (1920, 1080)},
            "output_ratio": "9:16",
            "max_clip_duration": 5,
            "max_total_video_duration": None,
            "crossfade_duration": 0.8,
            "enable_crossfade": True,  # <-- nova flag
            "max_clips": None,
            "shuffle_clips": True,
            "valid_extensions": ["mp4", "mkv", "avi", "mov", "flv", "webm"],
            "loop_background": False,
        }
        if params:
            defaults.update(params)
        if defaults["output_ratio"] in defaults["available_resolutions"]:
            defaults["resolution_output"] = defaults["available_resolutions"][defaults["output_ratio"]]
        for k, v in defaults.items():
            setattr(self, k, v)

    def load_and_resize_clip(self, video_path):
        try:
            video = VideoFileClip(video_path, audio=False)
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
            print(f"[ERRO] Falha em load_and_resize_clip: {e}")
            return None

    def apply_crossfade_transition(self, clips):
        if not clips:
            return None
        base = clips[0]
        for next_clip in clips[1:]:
            next_clip = next_clip.crossfadein(self.crossfade_duration).set_start(base.duration - self.crossfade_duration)
            base = CompositeVideoClip([base, next_clip]).set_duration(base.duration + next_clip.duration - self.crossfade_duration)
        return base

    def generate_background_video(self):
        # Lista de vídeos válidos
        video_files = [f for f in os.listdir(self.background_videos_dir)
                    if any(f.lower().endswith(ext) for ext in self.valid_extensions)]
        if not video_files:
            print("[ERRO] Nenhum arquivo de vídeo válido encontrado.")
            return None

        if self.shuffle_clips:
            random.shuffle(video_files)
        if self.max_clips:
            video_files = video_files[:self.max_clips]

        # Carregar e redimensionar clipes
        clips = []
        for video_name in video_files:
            path = os.path.join(self.background_videos_dir, video_name)
            clip = self.load_and_resize_clip(path)
            if clip:
                clips.append(clip)
            else:
                print(f"[ERRO] Falha ao carregar: {video_name}")

        if not clips:
            print("[ERRO] Nenhum clipe pôde ser carregado.")
            return None

        # Ajustar duração total considerando o crossfade:
        # A duração final = (soma das durações dos clipes) - (n_clips - 1)*crossfade_duration.
        if self.max_total_video_duration:
            final_duration = 0
            extended_clips = []
            idx = 0
            while True:
                clip = clips[idx % len(clips)]
                if extended_clips:
                    # Ao adicionar um novo clipe, perde-se crossfade_duration
                    nova_duracao = final_duration + clip.duration - self.crossfade_duration
                else:
                    nova_duracao = final_duration + clip.duration

                if nova_duracao >= self.max_total_video_duration:
                    # Ajusta o último clipe para que o vídeo fique exatamente com a duração desejada.
                    restante = self.max_total_video_duration - final_duration
                    if extended_clips:
                        restante += self.crossfade_duration  # recuperar o tempo de crossfade não utilizado
                    if restante < clip.duration:
                        clip = clip.subclip(0, restante)
                    extended_clips.append(clip)
                    break
                else:
                    extended_clips.append(clip)
                    final_duration = nova_duracao
                    idx += 1
            clips = extended_clips
        elif self.loop_background:
            # Repetir clipes algumas vezes para ter vídeo mais longo
            clips = clips * 3

        if self.enable_crossfade:
            final_video = self.apply_crossfade_transition(clips)
        else:
            final_video = concatenate_videoclips(clips, method='compose')
        return final_video

