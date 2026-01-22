import os
import base64
import wave
import json
import logging
from google import genai
from google.genai import types, errors
import dotenv

dotenv.load_dotenv()

# Configuração simples de logging para ver erros com timestamp
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Inicializa o cliente
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("A variável GEMINI_API_KEY não foi encontrada no arquivo .env")
    client = genai.Client(api_key=api_key)
except Exception as e:
    logging.error(f"Erro na inicialização do cliente: {e}")
    exit(1)

def print_formatted_error(error_obj):
    """
    Função auxiliar para imprimir erros ou objetos de resposta de forma bonita.
    """
    print("\n" + "="*40)
    print("Detalhes do Erro / Resposta da API:")
    print("="*40)
    
    # Tenta formatar como JSON se for possível
    try:
        # Se for um objeto da biblioteca Google GenAI que suporta to_json() ou model_dump()
        if hasattr(error_obj, 'model_dump_json'):
             print(error_obj.model_dump_json(indent=4))
        elif hasattr(error_obj, 'to_json'):
             print(error_obj.to_json(indent=4))
        elif isinstance(error_obj, (dict, list)):
            print(json.dumps(error_obj, indent=4, ensure_ascii=False))
        else:
            # Fallback para string normal
            print(str(error_obj))
    except Exception:
        print(str(error_obj))
    print("="*40 + "\n")

def generate_speech(text, voice_name="Kore"):
    print(f"🎙️  Gerando áudio para: '{text[:50]}...'")
    
    try:
        # Chamada da API
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp", 
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                )
            )
        )

        # Verifica se houve bloqueio ou resposta vazia
        if not response.candidates or not response.candidates[0].content.parts:
            logging.warning("A API respondeu, mas não retornou conteúdo. (Provável filtro de segurança)")
            print_formatted_error(response)
            return

        # Processamento do Áudio
        audio_found = False
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                audio_base64 = part.inline_data.data
                audio_bytes = base64.b64decode(audio_base64)
                
                filename = "output.wav"
                
                # Salvando como WAV
                with wave.open(filename, "wb") as wav_file:
                    wav_file.setnchannels(1)        # Mono
                    wav_file.setsampwidth(2)        # 16-bit
                    wav_file.setframerate(24000)    # 24kHz
                    wav_file.writeframes(audio_bytes)
                
                logging.info(f"Sucesso! Áudio salvo em: {os.path.abspath(filename)}")
                audio_found = True
                break
        
        if not audio_found:
            logging.error("Nenhuma parte de áudio encontrada na resposta.")
            print_formatted_error(response)

    except errors.ClientError as e:
        # Erros específicos da API do Google (ex: 403, 400, Quota Exceeded)
        logging.error("Erro na API do Google GenAI.")
        print_formatted_error(e)
        
    except Exception as e:
        # Erros genéricos de Python (ex: erro de escrita em disco)
        logging.error(f"Ocorreu um erro inesperado: {type(e).__name__}")
        print_formatted_error(e)

if __name__ == "__main__":
    generate_speech("Olá! Eu sou o Gemini e este script agora possui tratamento de erros completo.")