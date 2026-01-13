"""
ConfigManager - Gerenciador centralizado de configurações.

Este módulo centraliza o acesso a configurações e parâmetros,
facilitando o compartilhamento entre serviços.

Preserva compatibilidade total com Config existente.
"""

from libs.Config import Config


class ConfigManager:
    """
    Gerenciador centralizado de configurações.
    
    Wrapper sobre Config existente para facilitar acesso
    e compartilhamento de configurações entre serviços.
    """
    
    def __init__(self, data_config):
        """
        Inicializa o gerenciador de configurações.
        
        Args:
            data_config: Dicionário de configuração do vídeo
        """
        self.data_config = data_config
        self.config_instance = Config()
        
        # Aplicar configurações globais
        global_settings = data_config.get("global_settings", {})
        
        if "padding_bottom" in global_settings:
            self.config_instance.padding_bottom = global_settings["padding_bottom"]
        if "padding_top" in global_settings:
            self.config_instance.padding_top = global_settings["padding_top"]
        if "padding_side" in global_settings:
            self.config_instance.padding_side = global_settings["padding_side"]
        
        # Configurar resolução
        output_ratio = data_config.get("output_ratio", "9:16")
        available_resolutions = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
        resolution_output = available_resolutions.get(output_ratio, (1080, 1920))
        
        self.config_instance.width = resolution_output[0]
        self.config_instance.height = resolution_output[1]
    
    def get_config_instance(self):
        """Retorna instância de Config."""
        return self.config_instance
    
    def get_resolution(self):
        """Retorna resolução como tupla (width, height)."""
        return (self.config_instance.width, self.config_instance.height)
    
    def get_global_settings(self):
        """Retorna configurações globais."""
        return self.data_config.get("global_settings", {})
    
    def get_tts_config(self):
        """Retorna configuração de TTS."""
        return self.get_global_settings().get("tts", {})
