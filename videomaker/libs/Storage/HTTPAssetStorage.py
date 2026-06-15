import os
from datetime import datetime
from typing import List, Dict, Optional

import requests
from dotenv import load_dotenv

from libs.Storage.RemoteAssetStorage import RemoteAssetStorage

load_dotenv()


class HTTPAssetStorage(RemoteAssetStorage):
    """
    Implementação de RemoteAssetStorage que delega tudo para a API
    (módulo `assets`, endpoints internos sob /remote-assets/internal).

    A API é a fonte única da verdade — os mesmos registros gerenciados
    pelo painel web. Autenticação via header X-Service-Token.

    Config via .env do videomaker:
        API_BASE_URL   (default http://127.0.0.1:8000)
        SERVICE_TOKEN  (deve bater com o SERVICE_TOKEN da API)

    Mapeia o schema do banco (is_invalid, last_used) para o formato
    histórico esperado pelo RemoteAssetManager (invalid, lastUsed).
    """

    def __init__(self, base_url: Optional[str] = None, service_token: Optional[str] = None, timeout: int = 15):
        self.base_url = (base_url or os.getenv("API_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.service_token = service_token or os.getenv("SERVICE_TOKEN", "dev-service-token")
        self.timeout = timeout
        self._prefix = f"{self.base_url}/remote-assets/internal"
        self._headers = {"X-Service-Token": self.service_token}

    # -- helpers ----------------------------------------------------------
    def _midia_to_legacy(self, m: Dict) -> Dict:
        """Converte mídia da API (is_invalid/last_used) p/ formato legado (invalid/lastUsed)."""
        last_used = m.get("last_used")
        if isinstance(last_used, str):
            last_used = last_used.replace("T", " ")[:19]
        return {
            "url": m.get("url"),
            "type": m.get("type", "unknown"),
            "extension": m.get("extension"),
            "lastUsed": last_used or "1900-01-01 00:00:00",
            "invalid": bool(m.get("is_invalid")),
        }

    def _get(self, path: str):
        return requests.get(f"{self._prefix}{path}", headers=self._headers, timeout=self.timeout)

    # -- interface --------------------------------------------------------
    def get_slug(self, slug: str) -> Optional[Dict]:
        try:
            r = self._get(f"/by-slug/{slug}")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
            return {
                "slug": data.get("slug"),
                "description": data.get("description") or "",
                "media": [self._midia_to_legacy(m) for m in data.get("midias", [])],
            }
        except requests.RequestException as e:
            print(f"[HTTPAssetStorage] ❌ get_slug('{slug}'): {e}")
            return None

    def get_media_list(self, slug: str) -> List[Dict]:
        entry = self.get_slug(slug)
        return entry.get("media", []) if entry else []

    def add_media(self, slug: str, media: Dict, description: str = "") -> bool:
        try:
            payload = {
                "url": media.get("url"),
                "type": media.get("type", "unknown"),
                "extension": media.get("extension"),
                "description": description,
            }
            r = requests.post(
                f"{self._prefix}/by-slug/{slug}/midia",
                json=payload, headers=self._headers, timeout=self.timeout,
            )
            r.raise_for_status()
            return True
        except requests.RequestException as e:
            print(f"[HTTPAssetStorage] ❌ add_media('{slug}'): {e}")
            return False

    def mark_invalid(self, url: str) -> bool:
        try:
            r = requests.patch(
                f"{self._prefix}/midia/mark-invalid",
                json={"url": url}, headers=self._headers, timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json().get("affected", 0) > 0
        except requests.RequestException as e:
            print(f"[HTTPAssetStorage] ❌ mark_invalid: {e}")
            return False

    def update_last_used(self, url: str) -> bool:
        try:
            r = requests.patch(
                f"{self._prefix}/midia/touch",
                json={"url": url}, headers=self._headers, timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json().get("affected", 0) > 0
        except requests.RequestException as e:
            print(f"[HTTPAssetStorage] ❌ update_last_used: {e}")
            return False

    def cleanup_invalid(self, days_threshold: int = 7) -> int:
        # Limpeza é responsabilidade do painel/API; no-op no videomaker.
        return 0

    def url_exists(self, slug: str, url: str) -> bool:
        return any(m.get("url") == url for m in self.get_media_list(slug))

    def list_all_slugs(self) -> List[str]:
        try:
            r = self._get("/slugs")
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"[HTTPAssetStorage] ❌ list_all_slugs: {e}")
            return []

    def get_stats(self) -> Dict:
        try:
            r = self._get("/stats")
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"[HTTPAssetStorage] ❌ get_stats: {e}")
            return {"total_slugs": 0, "total_media": 0, "invalid_media": 0, "valid_media": 0}
