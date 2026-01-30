import json
from typing import Dict, List, Optional


def build_entity_index(prompt_entities: Dict) -> Dict[str, Dict]:
    index = {}

    for entity_type, entities in prompt_entities.items():
        singular = entity_type[:-1]  # characters -> character
        for entity in entities:
            key = f"{singular}:{entity['id']}"
            index[key] = entity

    return index


def build_scene_prompt(
    scene_use: List[str],
    entity_index: Dict[str, Dict]
) -> str:
    prompt_parts = []

    for item in scene_use:
        if ":" in item and item in entity_index:
            entity = entity_index[item]
            prompt_parts.append(
                entity.get("visual") or entity.get("description", "")
            )
        else:
            prompt_parts.append(item)

    final_prompt = ", ".join(prompt_parts)
    final_prompt += ", ultra detailed, high quality, cinematic composition"

    return final_prompt


def resolve_seed(
    scene: Dict,
    global_seed: Optional[int]
) -> Optional[int]:
    return scene.get("seed", global_seed)


def transform_json_to_scenes(input_json: Dict) -> List[Dict]:
    prompt_entities = input_json.get("prompt_entities", {})
    scenes = input_json.get("scenes", [])
    global_seed = input_json.get("seed")

    entity_index = build_entity_index(prompt_entities)
    final_scenes = []

    for idx, scene in enumerate(scenes, start=1):
        scene_id = str(idx).zfill(4)

        image_prompt = build_scene_prompt(
            scene_use=scene.get("use", []),
            entity_index=entity_index
        )

        seed = resolve_seed(scene, global_seed)

        visual_block = {
            "type": "ai",
            "provider": "pollinations",
            "content_type": "image",
            "prompt": image_prompt
        }

        if seed is not None:
            visual_block["parameters"] = {"seed": seed}

        final_scene = {
            "id": scene_id,
            "narration": {
                "text": scene.get("text", ""),
                "subtitles": True
            },
            "background": {
                "visual": visual_block
            }
        }

        final_scenes.append(final_scene)

    return final_scenes

def get_text_all_scenes(scenes: List[Dict]) -> str:
    # cada frase em uma linha
    # entre cada capitulo, uma linha em branco

    # frase cap 1
    # frase cap 1
    # 
    # frase cap 2
    # frase cap 2
    #  ...

    capitulos_lista = {}

    for scene in scenes:
        text = scene.get("text", "")
        cap = scene.get("cap", "")
        
        if cap not in capitulos_lista:
            capitulos_lista[cap] = []

        capitulos_lista[cap].append(text)

    # print(capitulos_lista)
    # exit()

    resultado = []
    for capitulo, frases in capitulos_lista.items():
        resultado.extend(frases)
        resultado.append("")  # linha em branco entre capítulos

    return "\n".join(resultado).strip()


    

# -------------------------
# USO
# -------------------------
if __name__ == "__main__":
    with open("input.json", "r", encoding="utf-8") as f:
        input_data = json.load(f)

    scenes_output = transform_json_to_scenes(input_data)

    with open("scenes_output.json", "w", encoding="utf-8") as f:
        json.dump(scenes_output, f, indent=2, ensure_ascii=False)

    # obter todo o texto das cenas
    all_text = get_text_all_scenes(input_data.get("scenes", []))

    with open("all_scenes_text.txt", "w", encoding="utf-8") as f:
        f.write(all_text)

    print("✅ Cenas geradas com seed aplicado corretamente.")
