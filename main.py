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
        # 3. Ler o JSON do Vídeo
        with open(args.json_file, 'r', encoding='utf-8') as f:
            video_data = json.load(f)
            
        print(f"📂 Processando arquivo: {args.json_file}")
        
    except json.JSONDecodeError as e:
        print(f"❌ Erro de Sintaxe no JSON: {e}")
        return

    # 4. Inicializar Configuração (Com Deep Merge automático)
    try:
        config = Config(video_data=video_data)
        config.validate() # Garante que pastas existem
        
        # Mostra configuração se o debug estiver ativo
        if config.debug:
            config.show_configs()
            
    except Exception as e:
        print(f"❌ Erro na Configuração: {e}")
        return

    # 5. Iniciar o Motor de Vídeo
    try:
        engine = UnifiedVideoEngine(config)
        engine.run()
    except Exception as e:
        print(f"❌ Erro durante a execução do motor: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()