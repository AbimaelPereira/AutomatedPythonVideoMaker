import os
import json
import sys

# composite imports
from moviepy.editor import CompositeVideoClip, CompositeAudioClip

from moviepy.editor import concatenate_videoclips

# Caminho absoluto até a raiz do projeto
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, ROOT)

# Agora pode importar
from libs.TemplateMaster import TemplateMaster

JSON_SCENES_LIBRARY_FILE = "./assets/scenes_library.json"
JSON = "./json_examples/product.json"
ASSETS_DIR = "./assets/"
SOUND_EFFECTS_PATH = os.path.join(ASSETS_DIR, "sound_effects/")

# load scenes library from JSON file
json_scenes_library = {}
if os.path.exists(JSON_SCENES_LIBRARY_FILE):
    with open(JSON_SCENES_LIBRARY_FILE, "r") as f:
        json_scenes_library = json.load(f)

# load video config from JSON file
video_config = {}
if os.path.exists(JSON):
    with open(JSON, "r") as f:
        video_config = json.load(f)[0]

TM = TemplateMaster({
    "output_folder": "./output/test_product",
    "slug": "test_product",
    "output_ratio": video_config.get("output_ratio", "9:16")
})

def renderize_scene(video):
    # verificar se a pasta existe
    if not os.path.exists(TM.output_folder):
        os.makedirs(TM.output_folder)

    video.write_videofile(
        os.path.join(TM.output_folder, "final_video.mp4"),
        codec="libx264",
        audio_codec="aac",
        fps=24,
        threads=2,
        temp_audiofile=os.path.join(TM.output_folder, "temp-audio.m4a"),
        remove_temp=True,
        bitrate="4000k",
        preset="superfast",
    )

    import subprocess

    subprocess.Popen(["xdg-open", os.path.join(TM.output_folder, "final_video.mp4")])

background = TM.generate_background_color("#FFDE59")

scenes = video_config.get("scenes")

FINAL_CLIPS = []

# add index to each scene
for index, scene in enumerate(scenes):
    index += 1

    GAP = 250
    audio_narration = None
    audio_sound_effect = None
    subtitle_clips = None
    visual_clip = None

    MAX_WIDTH = TM.width
    MAX_HEIGHT = TM.height


    if scene.get("use_scene_from_library") and scene["use_scene_from_library"] in json_scenes_library:
        scene_slug = scene["use_scene_from_library"]

        scene_data = json_scenes_library[scene_slug]
        scene_path = os.path.join(ASSETS_DIR, "scenes_library", scene_slug)

        # carregar narração
        if scene_data.get("narration_file"):
            narration_file = os.path.join(scene_path, scene_data["narration_file"])
            audio_narration = TM.load_audio_clip(narration_file)
            print(f"🔊 Áudio de narração carregado: {narration_file}")

        # carregar efeito sonoro
        if scene_data.get("sound_effect"):
            sound_effect_file = os.path.join(SOUND_EFFECTS_PATH, scene_data["sound_effect"])
            audio_sound_effect = TM.load_audio_clip(sound_effect_file)
            print(f"🔊 Efeito sonoro carregado: {sound_effect_file}")

        # redimensionar visual para 80% da largura e manter proporção
        if scene_data.get("visual"):
            visual_file = os.path.join(scene_path, scene_data["visual"])
            visual_clip = TM.load_visual_clip(visual_file)

            # largura do vídeo final * 0.8
            target_width = int(TM.width)
            visual_clip = visual_clip.resize(width=target_width)

        # carregar legenda
        if scene_data.get("subtitle_file") and scene_data["subtitle"]:
            subtitle_file = os.path.join(scene_path, scene_data["subtitle_file"])
            subtitle_clips = TM.load_subtitle_clip(subtitle_file)

            # legenda usa até 80% da largura também
            subtitle_clips = subtitle_clips.resize(width=int(TM.width * 0.8))
    
    else:
        scene_slug = "scene-" + str(index)
        print(f"⚠️ Cena '{scene_slug}' não encontrada na biblioteca de cenas.")

        scene_data = scene

        # TM.output_folder + slug da cena
        scene_path = os.path.join(TM.output_folder, scene_slug)
        # se não existir, criar
        if not os.path.exists(scene_path):
            os.makedirs(scene_path)

        if scene_data.get("narration_text"):
            narration_config = video_config.get("tts", {})
            narration_config["narration_text"] = scene_data["narration_text"]
            audio_and_subtitles = TM.narration_subtitles(narration_config)

            audio_narration = audio_and_subtitles["audio_narration"]

            if scene_data.get("subtitle"):
                subtitle_clips = audio_and_subtitles["subtitle_clips"]
        
        if scene_data.get("sound_effect"):
            sound_effect_file = os.path.join(SOUND_EFFECTS_PATH, scene_data["sound_effect"])
            audio_sound_effect = TM.load_audio_clip(sound_effect_file)
            print(f"🔊 Efeito sonoro carregado: {sound_effect_file}")

        if scene_data.get("visual"):
            visual_clip = TM.load_visual_clip(scene_data["visual"])

            target_width = int(TM.width * 0.8)
            visual_clip = visual_clip.resize(width=target_width)

    FINAL_VIDEO_SCENE = None

    # montar cena final
    if visual_clip and subtitle_clips:
        # posição vertical do visual (centralizado verticalmente)
        visual_y = (TM.height - (visual_clip.h + subtitle_clips.h + GAP)) // 2

        # legenda fica logo abaixo
        subtitle_y = visual_y + visual_clip.h + GAP

        # fade out into visual clip
        # visual_clip = visual_clip.fadeout(0.1)

        FINAL_VIDEO_SCENE = CompositeVideoClip([
            visual_clip.set_position(("center", visual_y)),
            subtitle_clips.set_position(("center", subtitle_y))
        ], size=(TM.width, TM.height))

    elif visual_clip:
        # apenas visual (centralizado)
        visual_y = (TM.height - visual_clip.h) // 2
        FINAL_VIDEO_SCENE = visual_clip.set_position(("center", visual_y)).set_duration(visual_clip.duration)

    elif subtitle_clips:
        # apenas legenda (centralizada total)
        subtitle_y = (TM.height - subtitle_clips.h) // 2
        FINAL_VIDEO_SCENE = subtitle_clips.set_position(("center", subtitle_y))

    FINAL_AUDIO_SCENE = None
    # áudio final
    if audio_narration and audio_sound_effect:
        FINAL_AUDIO_SCENE = CompositeAudioClip([
            audio_sound_effect,
            audio_narration
        ])
        print("🔊 Áudio mixado com narração e efeito sonoro")
    elif audio_narration:
        FINAL_AUDIO_SCENE = audio_narration
        print("🔊 Áudio com narração")
    elif audio_sound_effect:
        FINAL_AUDIO_SCENE = audio_sound_effect
        print("🔊 Áudio com efeito sonoro")

    # juntar com background
    if FINAL_VIDEO_SCENE:
        FINAL_VIDEO_SCENE = CompositeVideoClip([
            background.set_duration(FINAL_VIDEO_SCENE.duration),
            FINAL_VIDEO_SCENE
        ], size=(TM.width, TM.height))
        
    FINAL_VIDEO_SCENE = FINAL_VIDEO_SCENE.set_audio(FINAL_AUDIO_SCENE)
    FINAL_VIDEO_SCENE = FINAL_VIDEO_SCENE.set_duration(FINAL_AUDIO_SCENE.duration)

    FINAL_CLIPS.append(FINAL_VIDEO_SCENE)

# concatenar todas as cenas
final_video = concatenate_videoclips(FINAL_CLIPS, method="compose")

# renderizar vídeo final
renderize_scene(final_video)

