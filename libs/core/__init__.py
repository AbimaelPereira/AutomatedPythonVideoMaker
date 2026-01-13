"""
Core package - Componentes centrais da aplicação.

Este pacote contém os componentes centrais:
- ConfigManager: Gerenciamento de configurações
- VideoOrchestrator: Orquestração do fluxo de vídeo
"""

from .ConfigManager import ConfigManager
from .VideoOrchestrator import VideoOrchestrator

__all__ = [
    "ConfigManager",
    "VideoOrchestrator"
]
