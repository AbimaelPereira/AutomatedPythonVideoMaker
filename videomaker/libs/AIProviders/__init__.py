from .PollinationsProvider import PollinationsProvider
from .ModelScopeProvider import ModelScopeProvider
from .AIProviderManager import AIProviderManager, AIProvider
from .GeminiProvider import GeminiProvider

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

    # ModelScope — so' se houver token. Sem MODELSCOPE_TOKEN o provider nem e'
    # instanciado, para nao poluir o log de quem nao usa este provider.
    # NUNCA make_default: o default continua sendo o Pollinations, e a troca
    # e' explicita (provider="modelscope").
    if ModelScopeProvider.disponivel():
        try:
            ai_manager.register_provider("modelscope", ModelScopeProvider())
            print("✅ Provider ModelScope configurado")
        except Exception as e:
            print(f"⚠️ Erro ao configurar ModelScope: {e}")

    # Futuros providers podem ser adicionados aqui
    # try:
    #     openai_provider = OpenAIProvider()
    #     ai_manager.register_provider("openai", openai_provider)
    # except Exception as e: 
    #     print(f"⚠️ Erro ao configurar OpenAI: {e}")

# Auto-setup
setup_providers()

__all__ = ["ai_manager", "PollinationsProvider", "ModelScopeProvider", "AIProviderManager", "AIProvider", "GeminiProvider"]