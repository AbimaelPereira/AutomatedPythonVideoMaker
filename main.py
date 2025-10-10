# generate_from_json.py
import os
import json
from moviepy.editor import CompositeVideoClip, VideoFileClip, AudioFileClip, ImageClip, CompositeAudioClip

from libs.Config import Config
from libs.TTS_Edge import EdgeTTS  # <-- nova lib que criamos
from libs.BackgroundVideo import BackgroundVideo
from libs.Subtitle import Subtitle
from libs.Headline import Headline


import time


def process_video(cfg: Config, language: dict, output: dict, project_folder: str):
    print(f"\n🎬 Gerando vídeo para: {output['title']} ({output['output_ratio']})")

    # --- 1. Gerar áudio e legenda ---
    tts = EdgeTTS({
        "text": output["narration_text"],
        "voice_id": language["edge_tts"]["voice_id"],  # usando voz do Edge
    })
    tts_result = tts.generate_audio_and_subtitles()
    cfg.set_item("audio_narration_file", tts_result["audio_file"])
    cfg.set_item("subtitle_narration_file", tts_result["subtitle_file"])

    audio_narration = AudioFileClip(cfg.audio_narration_file)
    cfg.set_item("max_total_video_duration", audio_narration.duration)
    cfg.set_item("output_ratio", output["output_ratio"])

    # --- 2. Gera imagem da manchete ---
    headline = Headline({
        "output_path": "manchete_final.png",
        "title": language["headline"]["title"],
        "subtitle": language["headline"]["subtitle"]
    })
    headline_data = headline.generate()

    # --- 3. Monta os vídeos de fundo ---
    cfg.set_item("enable_crossfade", False)  # Habilita crossfade
    bg = BackgroundVideo(cfg.config)
    final_video = bg.generate_background_video()
    if not final_video:
        raise RuntimeError("Nenhum vídeo de fundo foi gerado.")
    

    # bg_clip = AudioFileClip("temp_files/bg_compressed.wav")
    # if bg_clip.duration < cfg.max_total_video_duration:
    #     # Loop para garantir que o áudio de fundo cubra toda a narração
    #     n_loops = int(cfg.max_total_video_duration // bg_clip.duration) + 1
    #     bg_clip = CompositeAudioClip([bg_clip] * n_loops)
    #     bg_clip = bg_clip.set_duration(cfg.max_total_video_duration)
    # # Corta o áudio de fundo para a duração máxima do vídeo
    # bg_clip = bg_clip.subclip(0, cfg.max_total_video_duration)

    # # --- MIXAGEM ---
    # # Ajusta volume da música de fundo se necessário
    # bg_clip = bg_clip.volumex(0.3)  # 30% do volume original

    # final_audio = CompositeAudioClip([bg_clip, audio_narration])

    # final_video = final_video.set_audio(final_audio)
    final_video = final_video.set_audio(audio_narration)
    final_video = final_video.resize(cfg.resolution_output)

    # --- 4. Monta o bloco com headline + legendas ---
    headline_clip = (
        ImageClip(headline_data["path"])
        .set_duration(cfg.max_total_video_duration)
        .set_opacity(cfg.manchete_opacity)
    )

    sub = Subtitle(cfg.config)
    subtitle_clips = sub.generate()
    subtitle_clips = subtitle_clips.resize(width=headline_clip.w).set_duration(cfg.max_total_video_duration)

    GAP = 200
    block = CompositeVideoClip([
        headline_clip,
        subtitle_clips.set_position(("center", headline_clip.h + GAP))
    ], size=(headline_clip.w, headline_clip.h + subtitle_clips.h + GAP))

    block = block.resize(width=int(cfg.width * 0.8))

    # --- 5. Composição final ---
    final = CompositeVideoClip([
        final_video,
        block.set_position(("center", int(final_video.h * 0.3 - block.h / 2)))
    ])

    # --- 6. Renderização ---
    language_folder = os.path.join(project_folder, language["path_name"])
    os.makedirs(language_folder, exist_ok=True)

    safe_title = output["title"].replace(" ", "_").lower()
    output_file = os.path.join(language_folder, f"{safe_title}_{cfg.output_ratio.replace(':', '_')}.mp4")

    print(f"[INFO] Gerando vídeo final: {output_file}")
    final.write_videofile(
        output_file,
        codec="libx264",
        audio_codec="aac",
        fps=25,
        threads=5,  # usa todos os threads da CPU
        temp_audiofile="temp-audio.m4a",
        remove_temp=True,
        bitrate="3000k",  # reduz um pouco o tamanho e melhora velocidade
        preset="superfast",  # quase tão rápido quanto ultrafast, mas com compressão melhor
    )

    print(f"✅ Vídeo final salvo como: {output_file}")


def main():
    # hora inicial
    print("[INFO] Iniciando o processo de geração de vídeos...")
    start_time = time.time()

    print("📂 Carregando arquivo de configuração JSON...")
    with open("temp/b.json", "r", encoding="utf-8") as f:
        config_data = json.load(f)

    for project in config_data:
        print(f"\n🔧 Iniciando projeto: {project['title_video']}")
        project_folder = os.path.join("output", project["title_video"].replace(" ", "_").lower())
        os.makedirs(project_folder, exist_ok=True)

        cfg = Config()
        cfg.set_item("background_videos_dir", project["background_videos_dir"])

        for language in project["languages"]:
            print(f"\n🌎 Idioma: {language['path_name']}")
            for output in language["outputs"]:
                cfg.set_item("output_ratio", output["output_ratio"])
                process_video(cfg, language, output, project_folder)

    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"\n🏁 Processo concluído em {elapsed_time:.2f} segundos")
if __name__ == "__main__":
    main()
