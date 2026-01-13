"""
UnifiedVideoEngine - Motor unificado de geração de vídeo (Refatorado).

Esta versão mantém compatibilidade total com a API original,
mas delega toda a lógica para o VideoOrchestrator modular.

Preserva:
- Mesma assinatura do construtor
- Mesmo método run() com mesmo retorno
- Mesma API pública
- Comportamento idêntico

A implementação original foi modularizada em:
- services/SpeechService.py: TTS e legendas
- services/AssetManager.py: Backgrounds, IA e cache
- services/SceneRenderer.py: Elementos visuais e overlays
- services/AudioEngine.py: Mixagem de áudio
- pipeline/ExportPipeline.py: Concatenação FFmpeg
- delivery/DeliveryService.py: Upload YouTube
- core/VideoOrchestrator.py: Orquestração
- core/ConfigManager.py: Configurações
"""

from libs.core.VideoOrchestrator import VideoOrchestrator


class UnifiedVideoEngine:
    """
    Motor unificado de geração de vídeo.
    
    API pública mantida para compatibilidade, mas implementação
    delegada ao VideoOrchestrator modular.
    """
    
    VALID_AUDIO_EXTENSIONS = [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"]
    
    def __init__(self, data_config):
        """
        Inicializa o motor de vídeo.
        
        Args:
            data_config: Dicionário ou objeto Config com configuração do vídeo
        """
        # Se receber um objeto Config, extrair o dicionário
        if hasattr(data_config, 'video_data'):
            self.data_config = data_config.video_data
        else:
            self.data_config = data_config
        
        # Criar orquestrador (faz toda a lógica)
        self.orchestrator = VideoOrchestrator(self.data_config)
        
        # Manter atributos para compatibilidade (se algo acessar)
        self.total_duration = 0.0
    
    def run(self, output_filename="final_video.mp4"):
        """
        Executa o fluxo completo de geração de vídeo.
        
        Args:
            output_filename: Nome do arquivo de saída
        
        Returns:
            Caminho do vídeo final ou None em caso de erro
        """
        print("[UVE] 🚀 Motor Unificado de Vídeo (Versão Modular)")
        
        # Delegar ao orquestrador
        final_path = self.orchestrator.run(output_filename)
        
        # Atualizar duração total para compatibilidade
        self.total_duration = self.orchestrator.total_duration
        
        return final_path
