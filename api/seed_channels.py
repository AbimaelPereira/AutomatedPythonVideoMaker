"""
Importa as configs de canal (channels_config/ e pastas dos canais) para o banco.
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

sys.path.insert(0, str(Path(__file__).parent.parent / "videomaker"))
from libs.utils import channel_config_files  # noqa: E402

DISPLAY_NAMES = {
    "blood_and_paperwork": "Blood & Paperwork",
    "devocional_com_jesus": "Devocional com Jesus",
    "hacker_patriota": "Hacker Patriota",
}

with Session(engine) as session:
    for slug, json_file in channel_config_files().items():
        existing = session.exec(select(Channel).where(Channel.slug == slug)).first()
        if existing:
            print(f"  skip  {slug} (já existe)")
            continue

        config = json.loads(Path(json_file).read_text())
        name = DISPLAY_NAMES.get(slug, slug.replace("_", " ").title())
        channel = Channel(slug=slug, name=name, config=json.dumps(config))
        session.add(channel)
        session.commit()
        print(f"  added {slug}")

print("Seed concluído.")
