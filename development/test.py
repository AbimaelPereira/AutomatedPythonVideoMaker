from moviepy.editor import ColorClip, CompositeVideoClip, VideoFileClip
from development.Filters import Filters

# Resolução final esperada (vertical)
RESOLUTION = (720, 1280)

# Carrega o vídeo e ajusta mantendo proporção, depois recorta para caber no frame 9:16
video = VideoFileClip("videos_default/futbool/2657261-uhd_3840_2160_24fps.mp4").subclip(0, 8)
video = video.resize(height=RESOLUTION[1])

# Centraliza e corta horizontalmente o excesso para manter proporção
video = video.crop(x_center=video.w / 2, width=RESOLUTION[0])

# Gera os overlays a partir do JSON
filters = Filters("FilterConfig.json", overlay_dir="FilterImages", resolution=RESOLUTION)

# Compor vídeo com overlays por cima
final = CompositeVideoClip([video] + filters.overlays, size=RESOLUTION)
final.write_videofile("teste_overlay.mp4", fps=60)
