"""Credenciais do Instagram (user_id + token) a partir de `instagram.credentials_json`.

`credentials_json` = caminho do arquivo (absoluto, `~`, ou relativo a videomaker/).
Arquivo: {"user_id": "...", "token": "...", "username": "..."}
Obrigatório: sem ele não há publicação (nada vem do .env).

CLI: python -m libs.InstagramAccount --check <caminho>
"""
import json
import os
from dataclasses import dataclass

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPH = "https://graph.facebook.com/v21.0"


@dataclass
class InstagramAccount:
    user_id: str
    token: str
    username: str | None = None
    source: str = ""


def credentials_file(path: str) -> str:
    return os.path.join(_BASE_DIR, os.path.expanduser(path))


def load_account(credentials_json: str | None = None) -> InstagramAccount:
    """Levanta ValueError com mensagem clara se faltar algo."""
    if not credentials_json:
        raise ValueError("instagram.credentials_json ausente (defina no JSON do vídeo ou no channels_config)")

    path = credentials_file(credentials_json)
    if not os.path.isfile(path):
        raise ValueError(f"Credenciais do Instagram não encontradas: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    token = data.get("token")
    faltando = [k for k, v in {"user_id": data.get("user_id"), "token": token}.items() if not v]
    if faltando:
        raise ValueError(f"Credenciais do Instagram em {path}: campos ausentes: {', '.join(faltando)}")
    return InstagramAccount(user_id=str(data["user_id"]), token=token,
                            username=data.get("username"), source=path)


def check(credentials_json: str) -> int:
    import requests
    from datetime import datetime

    acc = load_account(credentials_json)
    r = requests.get(f"{GRAPH}/{acc.user_id}", params={"fields": "username", "access_token": acc.token}, timeout=30)
    if not r.ok:
        print(f"❌ {r.status_code}: {r.text}")
        return 1
    print(f"✅ @{r.json().get('username')} (user_id={acc.user_id}, origem={acc.source})")

    d = requests.get(f"{GRAPH}/debug_token",
                     params={"input_token": acc.token, "access_token": acc.token}, timeout=30)
    if d.ok:
        info = d.json().get("data", {})
        exp = info.get("expires_at")
        print("   Expira: " + ("Nunca" if not exp else datetime.fromtimestamp(exp).isoformat()))
        print(f"   Escopos: {', '.join(info.get('scopes', []))}")
    else:
        print(f"   (debug_token indisponível: {d.status_code})")
    return 0


if __name__ == "__main__":
    import argparse
    import sys

    p = argparse.ArgumentParser()
    p.add_argument("--check", required=True, metavar="CREDENTIALS_JSON")
    sys.exit(check(p.parse_args().check))
