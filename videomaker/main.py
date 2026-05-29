import os
import json
import argparse
from libs.UnifiedVideoEngine import UnifiedVideoEngine


def main():
    parser = argparse.ArgumentParser(description="Automated Python Video Maker")
    parser.add_argument("json_file", help="Caminho para o arquivo JSON de geração do vídeo")
    args = parser.parse_args()

    # Resolve para absoluto antes do chdir, para que caminhos relativos passados
    # na linha de comando continuem funcionando.
    args.json_file = os.path.abspath(args.json_file)

    # Garante que caminhos relativos internos (tokens/, output/, cache/) resolvam
    # a partir do diretório do main.py, independente de onde o script é invocado.
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    if not os.path.exists(args.json_file):
        print(f"Erro Crítico: O arquivo '{args.json_file}' não foi encontrado.")
        return

    try:
        with open(args.json_file, "r", encoding="utf-8") as f:
            video_list = json.load(f)
        print(f"Processando arquivo: {args.json_file}")
    except json.JSONDecodeError as e:
        print(f"Erro de Sintaxe no JSON: {e}")
        return

    if not isinstance(video_list, list):
        video_list = [video_list]

    for index, video_data in enumerate(video_list):
        print(f"\nIniciando processamento do vídeo {index + 1}/{len(video_list)}...")
        try:
            engine = UnifiedVideoEngine(video_data)
            engine.run()
            print(f"Vídeo {index + 1} concluído com sucesso!")
        except Exception as e:
            print(f"Erro no vídeo {index + 1}: {e}")
            import traceback
            traceback.print_exc()
            continue


if __name__ == "__main__":
    main()