"""
Importa os arquivos de videomaker/channels_config/ para o banco de dados.
Rodar uma vez: python seed_channels.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database import engine
from sqlmodel import Session, select
from channels.models import Channel
import channels.models  # noqa: F401

from sqlmodel import SQLModel
SQLModel.metadata.create_all(engine)

CHANNELS_DIR = Path(__file__).parent.parent / "videomaker" / "channels_config"

DISPLAY_NAMES = {
    "broke_to_millionaire": "Broke to Millionaire",
    "devocional_com_jesus": "Devocional com Jesus",
    "hacker_patriota": "Hacker Patriota",
}

with Session(engine) as session:
    for json_file in CHANNELS_DIR.glob("*.json"):
        slug = json_file.stem
        existing = session.exec(select(Channel).where(Channel.slug == slug)).first()
        if existing:
            print(f"  skip  {slug} (já existe)")
            continue

        config = json.loads(json_file.read_text())
        name = DISPLAY_NAMES.get(slug, slug.replace("_", " ").title())
        channel = Channel(slug=slug, name=name, config=json.dumps(config))
        session.add(channel)
        session.commit()
        print(f"  added {slug}")

print("Seed concluído.")
