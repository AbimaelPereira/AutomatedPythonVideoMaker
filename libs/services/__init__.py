"""
Services package - Serviços modulares para geração de vídeo.

Este pacote contém todos os serviços especializados:
- SpeechService: TTS e legendas
- AssetManager: Backgrounds, IA e cache
- SceneRenderer: Elementos visuais e overlays
- AudioEngine: Mixagem de áudio
"""

from .SpeechService import SpeechService
from .AssetManager import AssetManager
from .SceneRenderer import SceneRenderer
from .AudioEngine import AudioEngine

__all__ = [
    "SpeechService",
    "AssetManager",
    "SceneRenderer",
    "AudioEngine"
]
