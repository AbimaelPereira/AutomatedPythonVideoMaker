import os
import hashlib

# Caminho da pasta de vídeos
path_videos = "/media/abimael/Grupo Win Lite BR/PAISAGENS/"

# Verifica se o diretório existe
if not os.path.isdir(path_videos):
    print(f"Diretório {path_videos} não encontrado.")
    exit()

# Lista de extensões de vídeo comuns
video_extensions = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"}

def generate_hash(filename):
    """Gera um hash curto para o nome do arquivo."""
    return hashlib.md5(filename.encode()).hexdigest()[:8]  # Usa os primeiros 8 caracteres do hash

# Lista para armazenar extensões encontradas
extensoes_encontradas = set()

# Percorre todos os arquivos na pasta
for filename in os.listdir(path_videos):
    file_path = os.path.join(path_videos, filename)
    
    # Ignora diretórios
    if not os.path.isfile(file_path):
        continue
    
    # Obtém a extensão do arquivo
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    
    # Verifica se é um vídeo
    if ext in video_extensions:
        extensoes_encontradas.add(ext)
        
        # Gera um novo nome baseado em hash
        new_name = generate_hash(filename) + ext
        new_path = os.path.join(path_videos, new_name)
        
        # Renomeia o arquivo
        os.rename(file_path, new_path)
        print(f"{filename} -> {new_name}")

# Lista todas as extensões encontradas
print("\nExtensões de vídeos encontradas:")
print(", ".join(extensoes_encontradas))