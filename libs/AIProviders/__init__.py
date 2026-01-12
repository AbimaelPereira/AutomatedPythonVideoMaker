from . PollinationsProvider import PollinationsProvider
from . AIProviderManager import AIProviderManager, AIProvider
from .AICache import AICache

# Setup automático do manager
ai_manager = AIProviderManager()

def setup_providers():
    """Inicializa todos os providers disponíveis"""
    try:
        # Pollinations
        pollinations = PollinationsProvider()
        ai_manager.register_provider("pollinations", pollinations, make_default=True)
        print("✅ Provider Pollinations configurado")
    except Exception as e: 
        print(f"⚠️ Erro ao configurar Pollinations: {e}")
    
    # Futuros providers podem ser adicionados aqui
    # try:
    #     openai_provider = OpenAIProvider()
    #     ai_manager.register_provider("openai", openai_provider)
    # except Exception as e: 
    #     print(f"⚠️ Erro ao configurar OpenAI: {e}")

# Auto-setup
setup_providers()

__all__ = ["ai_manager", "PollinationsProvider", "AIProviderManager", "AIProvider", "AICache"]