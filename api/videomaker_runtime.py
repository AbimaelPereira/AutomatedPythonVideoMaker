"""Interpretador e pasta do videomaker, compartilhados pelos módulos que rodam
o motor em SUBPROCESSO (thumbnail_preview, previews)."""

import os
import shutil
import subprocess
from typing import Optional

VIDEOMAKER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "videomaker")
)


class VideomakerPythonNotFound(RuntimeError):
    pass


# Interpretador já validado. O teste de import custa ~1s e o resultado não
# muda em runtime, então roda uma vez por processo.
_CACHED_PYTHON: Optional[str] = None


def _has_moviepy(python: str) -> bool:
    """Testa se o interpretador consegue importar MoviePy."""
    try:
        return subprocess.run(
            [python, "-c", "import moviepy"],
            capture_output=True, timeout=30,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def videomaker_python() -> str:
    """Interpretador que roda o videomaker.

    NÃO é o `sys.executable` da API: o videomaker exige `moviepy==1.0.3` com
    `numpy<2`, enquanto o venv da API traz numpy 1.26 e nenhum MoviePy.

    Cada candidato é VERIFICADO importando MoviePy, em vez de confiar no nome.
    Motivo: quando a API sobe com o venv ativado (é o que o `dev.sh` faz), um
    `which("python3")` resolve justamente para o python da API — sem MoviePy —
    e o render falharia com ModuleNotFoundError. Checar o que o interpretador
    realmente tem é a única forma de escolher certo em qualquer ambiente.

    Ordem: env `VIDEOMAKER_PYTHON` (respeitada sem teste, é escolha explícita)
    → venv do videomaker → pythons do sistema, fora do venv da API.
    """
    env_python = os.getenv("VIDEOMAKER_PYTHON")
    if env_python:
        return env_python

    global _CACHED_PYTHON
    if _CACHED_PYTHON:
        return _CACHED_PYTHON

    candidates = [
        os.path.join(VIDEOMAKER_DIR, ".venv", "bin", "python"),
        # Caminhos absolutos do sistema: imunes ao PATH do venv da API.
        "/usr/bin/python3",
        "/usr/local/bin/python3",
    ]
    # `which` por último e sem o venv da API no PATH, para não reencontrar o
    # interpretador que justamente não serve.
    clean_path = os.pathsep.join(
        p for p in os.environ.get("PATH", "").split(os.pathsep)
        if ".venv" not in p and "virtualenv" not in p
    )
    found = shutil.which("python3", path=clean_path)
    if found:
        candidates.append(found)

    for candidate in candidates:
        if os.path.exists(candidate) and _has_moviepy(candidate):
            _CACHED_PYTHON = candidate
            return candidate

    # Nenhum serve: falha com uma mensagem que diz o que fazer, em vez de
    # deixar o ModuleNotFoundError cru chegar ao usuário.
    raise VideomakerPythonNotFound(
        "Nenhum Python com MoviePy encontrado para renderizar. "
        "Defina VIDEOMAKER_PYTHON apontando para o interpretador do videomaker "
        "(o mesmo que roda `python main.py`)."
    )
