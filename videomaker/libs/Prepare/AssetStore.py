"""Cache de assets por vídeo: `{output}/{slug}/assets/` + `manifest.json`."""
import fcntl
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime

_SUBDIRS = {"ai": "ai", "download": "dl", "remote_asset": "dl"}


def _safe_name(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", key)


class AssetStore:
    """Índice `asset_key -> arquivo` com escrita atômica e lock entre processos.

    `enabled=False` faz `get` devolver None (força regeração); `put` continua
    gravando e sobrescreve a entrada antiga.
    """

    def __init__(self, assets_dir: str, *, enabled: bool = True):
        self.assets_dir = os.path.abspath(assets_dir)
        self.enabled = enabled
        self._manifest_path = os.path.join(self.assets_dir, "manifest.json")
        self._lock_path = os.path.join(self.assets_dir, ".lock")

    @contextmanager
    def _locked(self):
        os.makedirs(self.assets_dir, exist_ok=True)
        with open(self._lock_path, "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _read(self) -> dict:
        try:
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, ValueError):
            return {}

    def _write(self, entries: dict) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.assets_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(entries, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self._manifest_path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def _resolve_entry(self, entry: dict) -> str | None:
        if entry.get("kind") == "directory":
            path = (entry.get("meta") or {}).get("file")
        else:
            rel = entry.get("file")
            path = os.path.join(self.assets_dir, rel) if rel else None
        if path and os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
        return None

    def path_for(self, asset_key: str, kind: str, ext: str) -> str:
        sub = _SUBDIRS.get(kind, "dl")
        return os.path.join(self.assets_dir, sub, f"{_safe_name(asset_key)}.{ext.lstrip('.')}")

    def get(self, asset_key: str) -> str | None:
        if not self.enabled:
            return None
        if not os.path.exists(self._manifest_path):
            return None
        with self._locked():
            entries = self._read()
            entry = entries.get(asset_key)
            if not entry:
                return None
            path = self._resolve_entry(entry)
            if path is None:
                del entries[asset_key]
                self._write(entries)
            return path

    def put(self, asset_key: str, src_path_or_bytes, *, kind: str, ext: str = "",
            meta: dict | None = None) -> str:
        """Registra o asset. `kind="directory"` não copia nada: `meta["file"]` é o arquivo."""
        meta = dict(meta or {})
        if kind == "directory":
            rel = None
            result = meta.get("file")
            if not result:
                raise ValueError("kind='directory' exige meta['file']")
        else:
            dest = self.path_for(asset_key, kind, ext)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if isinstance(src_path_or_bytes, (bytes, bytearray)):
                fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest), suffix=".tmp")
                with os.fdopen(fd, "wb") as f:
                    f.write(src_path_or_bytes)
                os.replace(tmp, dest)
            elif os.path.abspath(src_path_or_bytes) != dest:
                fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest), suffix=".tmp")
                os.close(fd)
                shutil.copyfile(src_path_or_bytes, tmp)
                os.replace(tmp, dest)
            rel = os.path.relpath(dest, self.assets_dir)
            result = dest

        with self._locked():
            entries = self._read()
            entries[asset_key] = {
                "kind": kind,
                "file": rel,
                "created": datetime.now().isoformat(),
                "meta": meta,
            }
            self._write(entries)
        return result

    def entries(self) -> dict:
        if not os.path.exists(self._manifest_path):
            return {}
        with self._locked():
            return self._read()
