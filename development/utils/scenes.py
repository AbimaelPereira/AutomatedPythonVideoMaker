import os
import json
import sys

# Caminho absoluto até a raiz do projeto
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, ROOT)

# Agora pode importar
from libs.TemplateMaster import TemplateMaster

JSON_SCENES_LIBRARY_FILE = "./assets/scenes_library.json"

# load scenes library from JSON file
json_scenes_library = {}
if os.path.exists(JSON_SCENES_LIBRARY_FILE):
    with open(JSON_SCENES_LIBRARY_FILE, "r") as f:
        json_scenes_library = json.load(f)

SCENES_DIR = "./assets/scenes_library/"

# percorre as cenas
for scene_name, scene_data in json_scenes_library.items():
    print(f"Scene: {scene_name}")

    # verificar se existe a pasta da cena
    scene_path = os.path.join(SCENES_DIR, scene_name)
    if not os.path.exists(scene_path):
        os.makedirs(scene_path)

    narration_text = scene_data.get("narration_text", False)
    narration_file = os.path.join(scene_path, scene_name + ".mp3")
    subtitle_file = os.path.join(scene_path, scene_name + ".srt")

    TM = TemplateMaster({
        "output_folder": scene_path,
        "slug": scene_name
    })

    if narration_text and not os.path.exists(narration_file):
        # generate narration audio file and subtitle file
        # narration_subtitles
        a = TM.narration_subtitles({
            "narration_text": narration_text,
            "edge_tts": {
                "voice_id": "pt-BR-MacerioMultilingualNeural"
            }
        })

    