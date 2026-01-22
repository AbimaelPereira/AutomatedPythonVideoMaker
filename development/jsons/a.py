import json
import sys
from typing import List, Dict, Any

# Configuração
ARQUIVO_JSON_INPUT = "cenas_video1.json"
ARQUIVO_JSON_OUTPUT = "cenas_video1_formatado.json"

def gerar_cache_key(video_id: str, cena_numero: int) -> str:
    """
    Gera uma cache_key única para cada cena.
    
    Args:
        video_id: Identificador do vídeo (ex: "video1", "video2")
        cena_numero: Número da cena (começando em 1)
    
    Returns:
        String formatada como cache_key
    """
    return f"{video_id}_sc{cena_numero:02d}"

def gerar_scene_id(video_id: str, cena_numero: int) -> str:
    """
    Gera um ID único para cada cena.
    
    Args:
        video_id: Identificador do vídeo
        cena_numero: Número da cena
    
    Returns:
        String formatada como scene ID
    """
    return f"{video_id}_scene_{cena_numero:02d}"

def converter_cena(cena_original: Dict[str, str], video_id: str, numero_cena: int) -> Dict[str, Any]:
    """
    Converte uma cena do formato original para o formato desejado.
    
    Args:
        cena_original: Dicionário com 'text' e 'prompt_image'
        video_id: Identificador do vídeo
        numero_cena: Número sequencial da cena
    
    Returns:
        Dicionário no novo formato
    """
    cena_formatada = {
        "id": gerar_scene_id(video_id, numero_cena),
        "narration": {
            "text": cena_original["text"],
            "subtitles": True
        },
        "background": {
            "visual": {
                "type": "ai",
                "provider": "pollinations",
                "content_type": "image",
                "prompt": cena_original["prompt_image"],
                "parameters": {
                    "model": "zimage",
                    "width": 1080,
                    "height": 1920,
                    "safe": False
                },
                "cache_key": gerar_cache_key(video_id, numero_cena)
            }
        }
    }
    
    return cena_formatada

def processar_json(
    arquivo_entrada: str,
    arquivo_saida: str,
    video_id: str = "video1"
) -> None:
    """
    Processa o arquivo JSON de entrada e gera o arquivo formatado.
    
    Args:
        arquivo_entrada: Caminho do arquivo JSON original
        arquivo_saida: Caminho do arquivo JSON de saída
        video_id: Identificador do vídeo (padrão: "video1")
    """
    try:
        # Ler arquivo de entrada
        print(f"📖 Lendo arquivo: {arquivo_entrada}")
        with open(arquivo_entrada, 'r', encoding='utf-8') as f:
            cenas_originais = json.load(f)
        
        print(f"✅ {len(cenas_originais)} cenas encontradas")
        
        # Converter cada cena
        cenas_formatadas = []
        for i, cena in enumerate(cenas_originais, start=1):
            cena_formatada = converter_cena(cena, video_id, i)
            cenas_formatadas.append(cena_formatada)
            print(f"   ✓ Cena {i:02d} processada: {cena_formatada['id']}")
        
        # Salvar arquivo de saída
        print(f"\n💾 Salvando arquivo: {arquivo_saida}")
        with open(arquivo_saida, 'w', encoding='utf-8') as f:
            json.dump(cenas_formatadas, f, ensure_ascii=False, indent=2)
        
        print(f"\n🎉 Processo concluído com sucesso!")
        print(f"📊 Total de cenas convertidas: {len(cenas_formatadas)}")
        
    except FileNotFoundError:
        print(f"❌ ERRO: Arquivo '{arquivo_entrada}' não encontrado!")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ ERRO ao decodificar JSON: {e}")
        sys.exit(1)
    except KeyError as e:
        print(f"❌ ERRO: Campo obrigatório não encontrado: {e}")
        print("   Certifique-se de que cada cena tem 'text' e 'prompt_image'")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERRO inesperado: {e}")
        sys.exit(1)

def validar_cena(cena: Dict[str, str]) -> bool:
    """
    Valida se uma cena tem os campos obrigatórios.
    
    Args:
        cena: Dicionário da cena original
    
    Returns:
        True se válida, False caso contrário
    """
    return "text" in cena and "prompt_image" in cena

def main():
    """
    Função principal do script.
    """
    print("=" * 70)
    print("🎬 CONVERSOR DE CENAS - GEOPOLÍTICA EM FOCO")
    print("=" * 70)
    print()
    
    # Permitir argumentos de linha de comando
    if len(sys.argv) >= 2:
        arquivo_entrada = sys.argv[1]
    else:
        arquivo_entrada = ARQUIVO_JSON_INPUT
    
    if len(sys.argv) >= 3:
        arquivo_saida = sys.argv[2]
    else:
        # Gera nome de saída automaticamente
        arquivo_saida = arquivo_entrada.replace('.json', '_formatado.json')
    
    if len(sys.argv) >= 4:
        video_id = sys.argv[3]
    else:
        video_id = "video1"
    
    # Processar
    processar_json(arquivo_entrada, arquivo_saida, video_id)
    
    print()
    print("=" * 70)

if __name__ == "__main__":
    main()