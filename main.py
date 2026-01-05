import os
import json
import argparse
from libs.Config import Config
from libs.UnifiedVideoEngine import UnifiedVideoEngine

def main():
    # 1. Configurar Argumentos da Linha de Comando
    parser = argparse.ArgumentParser(description="Automated Python Video Maker")
    parser.add_argument("json_file", help="Caminho para o arquivo JSON de geração do vídeo")
    args = parser.parse_args()

    # 2. Validar Arquivo de Entrada
    if not os.path.exists(args.json_file):
        print(f"❌ Erro Crítico: O arquivo '{args.json_file}' não foi encontrado.")
        return

    try:
        with open(args.json_file, 'r', encoding='utf-8') as f:
            video_list = json.load(f) # Renomeado para video_list para clareza
            
        print(f"📂 Processando arquivo: {args.json_file}")
        
    except json.JSONDecodeError as e:
        print(f"❌ Erro de Sintaxe no JSON: {e}")
        return

    # Garantir que video_list seja sempre uma lista, mesmo que o JSON tenha só um objeto
    if not isinstance(video_list, list):
        video_list = [video_list]

    # Iterar sobre cada vídeo da lista
    for index, video_data in enumerate(video_list):
        print(f"\n🎬 Iniciando processamento do vídeo {index + 1}/{len(video_list)}...")
        
        try:
            # 4. Inicializar Configuração para o vídeo atual
            config = Config(video_data=video_data)
            config.validate()
            
            if config.debug:
                config.show_configs()

            # 5. Iniciar o Motor de Vídeo
            engine = UnifiedVideoEngine(config)
            engine.run()
            print(f"✅ Vídeo {index + 1} concluído com sucesso!")

        except Exception as e:
            print(f"❌ Erro no vídeo {index + 1}: {e}")
            import traceback
            traceback.print_exc()
            continue # Pula para o próximo vídeo se este falhar

if __name__ == "__main__":
    main()