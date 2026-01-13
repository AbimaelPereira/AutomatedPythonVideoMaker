"""
DeliveryService - Serviço responsável por entrega do vídeo (upload, etc.).

Este serviço encapsula toda a lógica relacionada a:
- Upload para YouTube
- Abertura do vídeo em modo debug
- Pós-processamento de entrega

Preserva o comportamento exato do UnifiedVideoEngine original em termos de:
- Parâmetros de upload do YouTube
- Logs e mensagens
- Comportamento de debug
"""

import os
import subprocess
from libs.YouTube import YouTube


class DeliveryService:
    """
    Serviço de entrega de vídeo.
    
    Responsável por upload do vídeo para plataformas
    e operações pós-processamento.
    """
    
    def __init__(self):
        """Inicializa o serviço de entrega."""
        pass
    
    def upload_to_youtube(self, video_path, youtube_config):
        """
        Faz upload do vídeo para o YouTube.
        
        Args:
            video_path: Caminho do vídeo a fazer upload
            youtube_config: Configuração de upload do YouTube
        
        Returns:
            True se sucesso, False se falhar
        """
        try:
            print("[DeliveryService] 📤 Iniciando upload para o YouTube...")
            
            youtube_params = youtube_config.copy()
            youtube_params["video_path"] = video_path
            
            youtube_uploader = YouTube(params=youtube_params)
            youtube_uploader.upload()
            
            print("[DeliveryService] ✅ Upload concluído com sucesso")
            return True
        
        except Exception as e:
            print(f"[DeliveryService] ❌ Upload YouTube falhou: {e}")
            return False
    
    def open_video_in_player(self, video_path):
        """
        Abre o vídeo no player padrão do sistema (modo debug).
        
        Args:
            video_path: Caminho do vídeo a abrir
        """
        try:
            print("[DeliveryService] 🎥 Abrindo vídeo final...")
            
            if os.name == 'nt':  # Windows
                os.startfile(video_path)
            elif os.name == 'posix':  # Linux/Mac
                if "darwin" in os.uname().sysname.lower():
                    subprocess.run(["open", video_path])
                else:
                    subprocess.run(["xdg-open", video_path])
        
        except Exception as e:
            print(f"[DeliveryService] ⚠️ Falha ao abrir vídeo: {e}")
