"""Worker de renderização de thumbnail — roda como SUBPROCESSO.

Existe como script separado de propósito: o motor de thumbnail puxa MoviePy, que
por sua vez fixa `numpy<2` e mantém handles de vídeo/ImageMagick abertos. Importar
isso dentro do processo da API contaminaria as dependências do backend e faria a
memória crescer a cada preview. Num subprocesso, tudo é liberado na saída.

Protocolo: lê o JSON da requisição no stdin, escreve no stdout uma última linha
JSON com `{"path": ..., "warnings": [...]}`. Erros vão para stderr com código de
saída != 0.

Os `warnings` existem porque as engines do videomaker são deliberadamente
tolerantes: um `source` inexistente vira fundo preto e um elemento inválido é
apenas pulado, ambos com um print e sem exceção. Isso é o certo durante um
render de vídeo longo (não se perde uma hora de trabalho por um asset), mas num
preview interativo devolveria um PNG preto sem explicação. Capturamos a saída
das engines e devolvemos as linhas de falha para a API mostrar ao usuário.
"""

import contextlib
import io
import json
import os
import sys

def main():
    payload = json.load(sys.stdin)

    videomaker_dir = payload["videomaker_dir"]
    # O videomaker resolve caminhos de asset/fonte relativos à sua própria pasta.
    os.chdir(videomaker_dir)
    sys.path.insert(0, videomaker_dir)

    import tempfile

    from libs.Preview.warnings import extract_warnings
    from libs.Thumbnail.Thumbnail import build_thumbnail, minimal_context

    work_dir = payload.get("work_dir") or tempfile.mkdtemp(prefix="thumb_worker_")
    video_resolution = (tuple(payload["video_resolution"])
                        if payload.get("video_resolution") else None)
    thumb = payload["thumbnail"]
    if video_resolution is None and thumb.get("width") and thumb.get("height"):
        # Sem vídeo de referência, a orientação vem da própria thumbnail.
        video_resolution = (int(thumb["width"]), int(thumb["height"]))
    ctx = minimal_context(work_dir, payload.get("global_settings") or {}, video_resolution)

    # As engines logam em stdout; capturamos para o resultado JSON continuar
    # sendo a última linha legível do stdout.
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        result = build_thumbnail(thumb, ctx, output_path=payload["output_path"])

    captured = log.getvalue()
    sys.stderr.write(captured)  # log completo fica disponível para diagnóstico

    if not result.path:
        sys.stderr.write("\n".join(result.warnings) + "\n")
        sys.exit(1)

    warnings = list(result.warnings)
    for line in extract_warnings(captured):
        if line not in warnings:
            warnings.append(line)
    json.dump({"path": result.path, "warnings": warnings}, sys.stdout)


if __name__ == "__main__":
    main()
