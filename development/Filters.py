import json
import os
from moviepy.editor import ImageClip, ColorClip
from moviepy.video.fx.all import fadein, fadeout

class Filters:
    def __init__(self, json_file_path, overlay_dir="Filters", resolution=(720, 1280)):
        self.json_file_path = json_file_path
        self.overlay_dir = overlay_dir
        self.resolution = resolution
        self.overlays = []
        self._load_filters()

    def _load_filters(self):
        try:
            with open(self.json_file_path, 'r', encoding='utf-8') as f:
                blocos = json.load(f)
        except Exception as e:
            print(f"[ERRO] Falha ao ler JSON: {e}")
            return

        for bloco in blocos:
            accumulated_time = 0

            for item in bloco:
                tipo = item.get("type")

                if tipo == "image":
                    file = item["file"]
                    duration = item["duration_seconds"]
                    fadein_perc = item.get("fade_in_percentage_of_image_duration", 0) / 100
                    fadeout_perc = item.get("fade_out_percentage_of_image_duration", 0) / 100

                    fadein_dur = duration * fadein_perc
                    fadeout_dur = duration * fadeout_perc
                    start_time = max(0, accumulated_time - fadein_dur)

                    path = os.path.join(self.overlay_dir, file)
                    if not os.path.isfile(path):
                        print(f"[AVISO] Arquivo não encontrado: {path}")
                        continue

                    clip = ImageClip(path).set_duration(duration).set_start(start_time)
                    clip = clip.set_position("center").resize(height=self.resolution[1])

                    if fadein_dur > 0:
                        clip = fadein(clip, fadein_dur)
                    if fadeout_dur > 0:
                        clip = fadeout(clip, fadeout_dur)

                    self.overlays.append(clip)
                    accumulated_time = start_time + duration - fadeout_dur

                elif tipo == "freeze":
                    duration = item.get("duration_seconds", 0)
                    if duration <= 0:
                        continue
                    # Cria um clip vazio invisível só pra pausar
                    dummy_clip = ColorClip(size=(1, 1), color=(0, 0, 0)).set_opacity(0)
                    dummy_clip = dummy_clip.set_duration(duration).set_start(accumulated_time)
                    self.overlays.append(dummy_clip)
                    accumulated_time += duration

                else:
                    print(f"[AVISO] Tipo desconhecido: {tipo}")
