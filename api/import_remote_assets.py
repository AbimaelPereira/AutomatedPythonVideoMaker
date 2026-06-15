"""
Importa os remote assets de videomaker/cache/remote_assets.json para o MySQL
(tabelas app_remote_assets e app_remote_assets_midia).

Idempotente: faz upsert do asset pelo slug e ignora URLs de mídia já existentes.

Uso:
    cd api && .venv/bin/python import_remote_assets.py
    .venv/bin/python import_remote_assets.py --dry-run
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session

from database import engine

JSON_PATH = Path(__file__).resolve().parent.parent / "videomaker" / "cache" / "remote_assets.json"

# extension é varchar(20) no banco; URLs com query string viram lixo no JSON.
MAX_EXTENSION_LEN = 20


def slug_to_name(slug: str) -> str:
    """Gera um nome legível a partir do slug (ex: 'banco_master' -> 'Banco Master')."""
    return slug.replace("_", " ").replace("-", " ").strip().title() or slug


def sanitize_extension(ext) -> str | None:
    if not ext:
        return None
    ext = str(ext)
    # extensões "sujas" (query strings, paths) excedem 20 chars -> descarta
    if len(ext) > MAX_EXTENSION_LEN:
        return None
    return ext


def parse_last_used(value) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def main(dry_run: bool = False):
    if not JSON_PATH.exists():
        raise SystemExit(f"Arquivo não encontrado: {JSON_PATH}")

    with open(JSON_PATH, encoding="utf-8") as f:
        groups = json.load(f)

    now = datetime.utcnow()
    stats = {"assets_new": 0, "assets_existing": 0, "media_new": 0, "media_skipped": 0}

    with Session(engine) as session:
        for group in groups:
            slug = group.get("slug")
            if not slug:
                continue
            description = group.get("description") or None

            # Upsert do asset pelo slug
            row = session.execute(
                text("SELECT id FROM app_remote_assets WHERE slug = :slug"),
                {"slug": slug},
            ).first()

            if row:
                asset_id = row[0]
                stats["assets_existing"] += 1
            else:
                if dry_run:
                    asset_id = None
                    stats["assets_new"] += 1
                else:
                    session.execute(
                        text(
                            "INSERT INTO app_remote_assets (name, slug, description, created_at, updated_at) "
                            "VALUES (:name, :slug, :description, :now, :now)"
                        ),
                        {"name": slug_to_name(slug), "slug": slug, "description": description, "now": now},
                    )
                    asset_id = session.execute(text("SELECT LAST_INSERT_ID()")).scalar()
                    stats["assets_new"] += 1
                print(f"[+] asset: {slug}")

            # URLs já existentes nesse asset (evita duplicar)
            existing_urls = set()
            if asset_id is not None:
                existing_urls = {
                    r[0]
                    for r in session.execute(
                        text("SELECT url FROM app_remote_assets_midia WHERE id_asset = :aid"),
                        {"aid": asset_id},
                    ).all()
                }

            for media in group.get("media", []):
                url = media.get("url")
                if not url:
                    continue
                if url in existing_urls:
                    stats["media_skipped"] += 1
                    continue

                params = {
                    "id_asset": asset_id,
                    "url": url,
                    "type": media.get("type") or "unknown",
                    "extension": sanitize_extension(media.get("extension")),
                    "is_invalid": 1 if media.get("invalid") else 0,
                    "last_used": parse_last_used(media.get("lastUsed")),
                    "created_at": now,
                }
                if not dry_run:
                    session.execute(
                        text(
                            "INSERT INTO app_remote_assets_midia "
                            "(id_asset, url, type, extension, is_invalid, last_used, created_at) "
                            "VALUES (:id_asset, :url, :type, :extension, :is_invalid, :last_used, :created_at)"
                        ),
                        params,
                    )
                existing_urls.add(url)
                stats["media_new"] += 1

        if dry_run:
            session.rollback()
            print("\n[dry-run] nada foi gravado.")
        else:
            session.commit()

    print(
        f"\nResumo: assets novos={stats['assets_new']}, existentes={stats['assets_existing']}, "
        f"mídias novas={stats['media_new']}, ignoradas (já existiam)={stats['media_skipped']}"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Simula sem gravar no banco")
    args = ap.parse_args()
    main(dry_run=args.dry_run)
