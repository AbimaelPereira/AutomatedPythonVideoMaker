"""Worker de renderização de thumbnail — roda como SUBPROCESSO.

Existe como script separado de propósito: o `ThumbnailRenderer` puxa MoviePy, que
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

# Trechos que marcam uma degradação silenciosa nas engines.
_WARNING_MARKERS = (
    "Falha ao criar fundo",
    "Fallback: preto",
    "Tipo de fundo desconhecido",
    "Erro no elemento",
    "Falha ao posicionar elemento",
    "Falha no LayoutEngine",
    "não encontrado",
    "não encontrada",
)


def _extract_warnings(log: str) -> list:
    seen, warnings = set(), []
    for line in log.splitlines():
        line = line.strip()
        if not line or line in seen:
            continue
        if any(marker in line for marker in _WARNING_MARKERS):
            seen.add(line)
            warnings.append(line)
    return warnings


def main():
    payload = json.load(sys.stdin)

    videomaker_dir = payload["videomaker_dir"]
    # O videomaker resolve caminhos de asset/fonte relativos à sua própria pasta.
    os.chdir(videomaker_dir)
    sys.path.insert(0, videomaker_dir)

    from libs.Thumbnail import ThumbnailRenderer

    # As engines logam em stdout; capturamos para o resultado JSON continuar
    # sendo a última linha legível do stdout.
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        path = ThumbnailRenderer.render(
            payload["thumbnail"],
            payload["output_path"],
            global_settings=payload.get("global_settings") or {},
            work_dir=payload.get("work_dir"),
            video_resolution=(tuple(payload["video_resolution"])
                              if payload.get("video_resolution") else None),
            log_prefix="[ThumbPreview]",
        )

    captured = log.getvalue()
    sys.stderr.write(captured)  # log completo fica disponível para diagnóstico

    json.dump({"path": path, "warnings": _extract_warnings(captured)}, sys.stdout)


if __name__ == "__main__":
    main()
