"""MediaProbe — metadados de mídia (duração/dimensões) sem abrir o arquivo no MoviePy.

O caminho MoviePy sabe a duração de graça (`VideoFileClip.duration`), mas paga
o custo de decodificar o arquivo. O caminho ffmpeg precisa saber a duração
ANTES de montar o filtergraph — e abrir um VideoFileClip só para ler metadado
anularia justamente o ganho de performance.

Este módulo lê os metadados via `ffprobe` (barato, não decodifica vídeo) e
cacheia em disco por `(path, mtime, size)`. Uma pasta com 200 clipes paga o
ffprobe uma vez na vida, não uma vez por cena.

O cache é compartilhado entre processos (o pipeline roda cenas em
`ProcessPoolExecutor`), então a escrita é atômica: grava num temporário e
troca com `os.replace`, que é atômico no mesmo filesystem. Duas escritas
concorrentes podem fazer uma perder entradas da outra, mas nunca corrompem o
arquivo — e a entrada perdida só custa um ffprobe a mais depois.
"""

import json
import os
import subprocess
import tempfile

_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"}


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _VIDEO_EXTS


def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _IMAGE_EXTS


def is_media(path: str) -> bool:
    return is_video(path) or is_image(path)


class MediaProbe:
    """Lê e cacheia metadados de mídia. Instância barata; o estado vive em disco."""

    def __init__(self, cache_path: str = "cache/media_probe.json"):
        self.cache_path = cache_path
        self._cache = self._load()
        self._dirty = False

    # -- persistência ------------------------------------------------------

    def _load(self) -> dict:
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            # Cache ausente/corrompido não é erro: só significa recomeçar do zero.
            return {}

    def save(self):
        """Grava o cache. Chamar uma vez ao fim do uso, não a cada probe."""
        if not self._dirty:
            return
        try:
            directory = os.path.dirname(os.path.abspath(self.cache_path))
            os.makedirs(directory, exist_ok=True)

            # Relê antes de gravar para não descartar o que outro processo
            # escreveu enquanto este rodava.
            merged = self._load()
            merged.update(self._cache)

            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(merged, f)
                os.replace(tmp, self.cache_path)
            except Exception:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
            self._dirty = False
        except Exception as e:
            print(f"[MediaProbe] ⚠️ Falha ao gravar cache: {e}")

    # -- leitura -----------------------------------------------------------

    def _key(self, path: str) -> str:
        """Chave que invalida sozinha quando o arquivo muda."""
        try:
            st = os.stat(path)
            return f"{os.path.abspath(path)}|{int(st.st_mtime)}|{st.st_size}"
        except OSError:
            return os.path.abspath(path)

    def probe(self, path: str) -> dict:
        """Metadados de um arquivo: {duration, width, height, is_video}.

        `duration` é None para imagem (não tem duração própria — quem chama
        decide via `image_default_duration`). Falha de leitura devolve dict com
        `duration: None` e dimensões 0, para o chamador tratar como inutilizável
        sem precisar capturar exceção.
        """
        key = self._key(path)
        if key in self._cache:
            return self._cache[key]

        info = self._ffprobe(path)
        self._cache[key] = info
        self._dirty = True
        return info

    def _ffprobe(self, path: str) -> dict:
        video = is_video(path)
        result = {"duration": None, "width": 0, "height": 0, "is_video": video}

        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error",
                 "-select_streams", "v:0",
                 "-show_entries", "stream=width,height,duration",
                 "-show_entries", "format=duration",
                 "-of", "json", path],
                capture_output=True, text=True, check=True, timeout=30,
            )
            data = json.loads(out.stdout or "{}")

            streams = data.get("streams") or []
            if streams:
                result["width"] = int(streams[0].get("width") or 0)
                result["height"] = int(streams[0].get("height") or 0)

            if video:
                # A duração do container (format) é mais confiável que a do
                # stream, que vem ausente em alguns codecs/muxers.
                duration = (data.get("format") or {}).get("duration")
                if duration is None and streams:
                    duration = streams[0].get("duration")
                if duration is not None:
                    value = float(duration)
                    result["duration"] = value if value > 0 else None
        except Exception as e:
            print(f"[MediaProbe] ⚠️ ffprobe falhou em {path}: {e}")

        return result

    def list_media(self, directory: str) -> list:
        """Arquivos de mídia da pasta (recursivo), em ordem estável.

        A ordem é ordenada — não a do filesystem — para que uma seleção com
        seed produza o mesmo resultado em máquinas diferentes.
        """
        if not os.path.isdir(directory):
            return []
        found = []
        for root, _, filenames in os.walk(directory):
            for name in filenames:
                full = os.path.join(root, name)
                if is_media(full):
                    found.append(full)
        return sorted(found)
