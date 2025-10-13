import os
from dotenv import load_dotenv
from moviepy.editor import VideoFileClip

load_dotenv()

PATH_VIDEOS = os.getenv("PATH_VIDEOS", "Videos Default/PAISAGENS/")
if not os.path.isdir(PATH_VIDEOS):
    print(f"Diretório {PATH_VIDEOS} não encontrado.")
    exit(1)

LIST_VIDEOS_DEFAULT = os.listdir(PATH_VIDEOS)

MAX_DURATION = 6  # segundos

for video_file in LIST_VIDEOS_DEFAULT:
    video_path = os.path.join(PATH_VIDEOS, video_file)
    if not video_file.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
        continue

    clip = VideoFileClip(video_path)
    duration = clip.duration

    if duration > MAX_DURATION:
        print(f"Cortando vídeo {video_file} de {duration:.2f}s para {MAX_DURATION}s")
        clip_cortado = clip.subclip(0, MAX_DURATION)

        # Sobrescreve o arquivo original
        clip_cortado.write_videofile(video_path, codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True)
        
        clip_cortado.close()
    else:
        print(f"Vídeo {video_file} com duração menor ou igual a {MAX_DURATION}s, não cortado.")
    
    clip.close()
