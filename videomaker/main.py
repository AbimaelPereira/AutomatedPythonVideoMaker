import os
import sys
import json
import argparse
from libs.UnifiedVideoEngine import UnifiedVideoEngine


def main():
    parser = argparse.ArgumentParser(description="Automated Python Video Maker")
    parser.add_argument("json_file", help="Caminho para o arquivo JSON de geração do vídeo")
    # Atalhos de iteração do Motion: resolver/validar o movimento custa
    # milissegundos, renderizar custa minutos. Ver libs/Motion/inspect.py.
    parser.add_argument("--timeline-only", action="store_true",
                        help="resolve e imprime as timelines de motion e sai (gera só a narração)")
    parser.add_argument("--validate", action="store_true",
                        help="só valida o schema de motion (sem TTS e sem render)")
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

    if args.validate or args.timeline_only:
        from libs.Motion.inspect import inspect_json

        count = len(video_list) if isinstance(video_list, list) else 1
        status = 0
        for index in range(count):
            status |= inspect_json(args.json_file, video_index=index,
                                   use_tts=not args.validate,
                                   validate_only=args.validate)
        return status

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
    # `--validate`/`--timeline-only` devolvem código de saída (útil em CI/pre-commit).
    sys.exit(main() or 0)
