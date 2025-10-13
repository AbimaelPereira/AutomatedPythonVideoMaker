import json
import os
import subprocess

DIR_SAVE_VIDEOS = "/media/abimael/Grupo Win Lite BR/videos"
JSO_FILE = "myJson.json"

# Carregar JSON se existir
data = []
if os.path.exists(JSO_FILE):
    with open(JSO_FILE, 'r') as f:
        data = json.load(f)

if not data:
    print("Nenhuma URL encontrada no arquivo JSON.")
    exit(1)

# Garantir que o diretório existe
os.makedirs(DIR_SAVE_VIDEOS, exist_ok=True)

# Baixar todos os vídeos
for video_url in data:
    print(f"Baixando vídeo: {video_url}")
    try:
        subprocess.run(
            ["yt-dlp", "-o", f"{DIR_SAVE_VIDEOS}/%(title)s.%(ext)s", video_url],
            check=True
        )
        print(f"✅ Vídeo baixado com sucesso: {video_url}")
    except subprocess.CalledProcessError:
        print(f"❌ Erro ao baixar: {video_url}")
