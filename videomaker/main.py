import os
import sys
import json
import argparse


def main():
    parser = argparse.ArgumentParser(description="Automated Python Video Maker")
    parser.add_argument("json_file", help="Caminho para o arquivo JSON de geração do vídeo")
    # Atalhos de iteração do Motion: resolver/validar o movimento custa
    # milissegundos, renderizar custa minutos. Ver libs/Motion/inspect.py.
    parser.add_argument("--timeline-only", action="store_true",
                        help="resolve e imprime as timelines de motion e sai (gera só a narração)")
    parser.add_argument("--validate", action="store_true",
                        help="só valida o schema de motion (sem TTS e sem render)")
    parser.add_argument("--prepare", action="store_true",
                        help="só resolve os assets visuais em {output}/{slug}/assets/ e imprime JSON")
    parser.add_argument("--scenes", default=None,
                        help="ids ou índices 1-based separados por vírgula (com --prepare)")
    parser.add_argument("--force", action="store_true",
                        help="ignora o cache e regera/baixa de novo (com --prepare)")
    args = parser.parse_args()

    # Resolve para absoluto antes do chdir, para que caminhos relativos passados
    # na linha de comando continuem funcionando.
    args.json_file = os.path.abspath(args.json_file)

    # Garante que caminhos relativos internos (tokens/, output/, cache/) resolvam
    # a partir do diretório do main.py, independente de onde o script é invocado.
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    if not os.path.exists(args.json_file):
        print(f"Erro Crítico: O arquivo '{args.json_file}' não foi encontrado.")
        return 1

    try:
        with open(args.json_file, "r", encoding="utf-8") as f:
            video_list = json.load(f)
        print(f"Processando arquivo: {args.json_file}")
    except json.JSONDecodeError as e:
        print(f"Erro de Sintaxe no JSON: {e}")
        return 1

    if args.validate or args.timeline_only:
        from libs.Motion.inspect import inspect_json

        count = len(video_list) if isinstance(video_list, list) else 1
        status = 0
        for index in range(count):
            status |= inspect_json(args.json_file, video_index=index,
                                   use_tts=not args.validate,
                                   validate_only=args.validate)
        return status

    if args.prepare:
        return run_prepare(video_list, args)

    from libs.UnifiedVideoEngine import UnifiedVideoEngine

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


def _parse_scenes(raw):
    if not raw:
        return None
    return [int(t) if t.strip().isdigit() else t.strip() for t in raw.split(",") if t.strip()]


def run_prepare(video_list, args) -> int:
    """`--prepare`: última linha do stdout = JSON do PrepareResult (array p/ lista)."""
    from libs.VideoContext import VideoContext
    from libs.Prepare.PrepareEngine import PrepareEngine

    is_list = isinstance(video_list, list)
    results = []
    try:
        for video_data in (video_list if is_list else [video_list]):
            ctx = VideoContext.from_video_data(video_data)
            indexes = ctx.select_scenes(_parse_scenes(args.scenes)) if args.scenes else None
            results.append(PrepareEngine(ctx, scene_indexes=indexes, force=args.force).run().to_json())
    except ValueError as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1
    print(json.dumps(results if is_list else results[0], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    # `--validate`/`--timeline-only` devolvem código de saída (útil em CI/pre-commit).
    sys.exit(main() or 0)
