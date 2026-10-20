"""Worker de preview/prepare — roda como SUBPROCESSO (MoviePy fora do processo da API).

Protocolo: stdin = JSON `{"videomaker_dir", "video", "scenes", "force", "mode"}`
(`mode`: "preview" | "prepare"). stdout: última linha = JSON
`{"mode", "output_dir", "result"}`. Logs das engines vão para stderr.
Saída 2 = requisição inválida (ValueError); outro código ≠ 0 = falha.
"""

import contextlib
import json
import os
import sys


def main():
    payload = json.load(sys.stdin)
    videomaker_dir = payload["videomaker_dir"]
    os.chdir(videomaker_dir)
    sys.path.insert(0, videomaker_dir)

    mode = payload.get("mode", "preview")
    scenes = payload.get("scenes")
    force = bool(payload.get("force"))

    try:
        with contextlib.redirect_stdout(sys.stderr):
            from libs.VideoContext import VideoContext

            ctx = VideoContext.from_video_data(payload["video"])
            if mode == "prepare":
                from libs.Prepare.PrepareEngine import PrepareEngine
                indexes = ctx.select_scenes(scenes) if scenes is not None else None
                result = PrepareEngine(ctx, scene_indexes=indexes, force=force).run().to_json()
            elif mode == "preview":
                from libs.Preview.PreviewEngine import PreviewEngine
                result = PreviewEngine(ctx, scenes=scenes, force=force).run().to_json()
            else:
                raise ValueError(f"mode inválido: {mode}")
    except ValueError as e:
        sys.stderr.write(f"ValueError: {e}\n")
        sys.exit(2)

    sys.stdout.write("\n" + json.dumps(
        {"mode": mode, "output_dir": ctx.output_dir, "result": result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
