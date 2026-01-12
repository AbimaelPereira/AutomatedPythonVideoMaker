from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

class AIProvider(ABC):
    """Classe abstrata para providers de IA"""
    
    @abstractmethod
    def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]: 
        pass
    
    @abstractmethod
    def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        pass

class AIProviderManager:
    """
    Gerenciador central para diferentes providers de IA
    Facilita a adição de novos providers no futuro
    """
    
    def __init__(self):
        self.providers: Dict[str, AIProvider] = {}
        self.default_provider:  Optional[str] = None
    
    def register_provider(self, name: str, provider:  AIProvider, make_default: bool = False):
        """Registra um novo provider"""
        self.providers[name] = provider
        if make_default or not self.default_provider:
            self. default_provider = name
    
    def get_provider(self, name: Optional[str] = None) -> AIProvider:
        """Obtém um provider específico ou o padrão"""
        provider_name = name or self.default_provider
        if not provider_name or provider_name not in self.providers:
            raise ValueError(f"Provider '{provider_name}' não encontrado")
        return self.providers[provider_name]
    
    def generate_image(self, prompt: str, provider: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Gera imagem usando o provider especificado"""
        return self.get_provider(provider).generate_image(prompt, **kwargs)
    
    def generate_video(self, prompt:  str, provider: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Gera vídeo usando o provider especificado"""
        return self.get_provider(provider).generate_video(prompt, **kwargs)