import os
from libs.TTS_Edge import EdgeTTS

# Garante que a pasta output existe para não dar erro de caminho
os.makedirs("output", exist_ok=True)

print("--- Iniciando Teste de Debug TTS ---")

params = {
    # Usando uma voz garantida
    "voice_id": "pt-BR-AntonioNeural",
    "text": "Este é um teste de depuração do sistema de vídeo...",
    # Salva na pasta output para não sujar a raiz
    "output_basename": "output/teste_debug"
}

try:
    print(f"Tentando gerar audio com voz: {params['voice_id']}...")
    tts = EdgeTTS(params=params)
    
    # Chama o método que o UnifiedVideoEngine chama
    resultado = tts.generate_audio_and_subtitles()
    
    print("\n✅ SUCESSO!")
    print(f"Arquivo de áudio: {resultado['audio_file']}")
    print(f"Arquivo de legenda: {resultado['subtitle_file']}")
    
except Exception as e:
    print("\n❌ ERRO FATAL:")
    print(e)