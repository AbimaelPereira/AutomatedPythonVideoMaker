import os
import json
import time
from moviepy.editor import CompositeVideoClip, AudioFileClip, ImageClip

from libs.Config import Config
from libs.TTS_Edge import EdgeTTS
from libs.BackgroundVideo import BackgroundVideo
from libs.Subtitle import Subtitle
from libs.Headline import Headline


def process_video(cfg: Config, video_config: dict, output_folder: str):
    """
    Processa um único vídeo com base na configuração fornecida.
    
    Args:
        cfg: Objeto de configuração
        video_config: Dicionário com as configurações do vídeo
        output_folder: Pasta onde o vídeo será salvo
    """
    print(f"\n🎬 Gerando vídeo: {video_config['title'][:50]}...")
    print(f"📐 Proporção: {video_config.get('output_ratio', '9:16')}")

    # --- 1. Configurar diretório de vídeos de fundo ---
    cfg.set_item("background_videos_dir", video_config["background_videos_dir"])
    cfg.set_item("output_ratio", video_config.get("output_ratio", "9:16"))

    # --- 2. Gerar áudio e legenda com Edge TTS ---
    edge_tts_config = video_config.get("edge_tts", {})
    voice_id = edge_tts_config.get("voice_id", "pt-BR-AntonioNeural")
    
    print(f"🗣️  Gerando áudio com voz: {voice_id}")
    tts = EdgeTTS({
        "text": video_config["narration_text"],
        "voice_id": voice_id,
        "output_basename": f"{video_config['slug']}"
    })
    tts_result = tts.generate_audio_and_subtitles()
    
    cfg.set_item("audio_narration_file", tts_result["audio_file"])
    cfg.set_item("subtitle_narration_file", tts_result["subtitle_file"])

    # --- 3. Carregar áudio e definir duração do vídeo ---
    audio_narration = AudioFileClip(cfg.audio_narration_file)
    cfg.set_item("max_total_video_duration", audio_narration.duration)
    print(f"⏱️  Duração do áudio: {audio_narration.duration:.2f}s")

    # verica se background_music_file
    has_bg_music = "background_music_file" in video_config and video_config["background_music_file"]
    if has_bg_music:
        if not os.path.exists(video_config["background_music_file"]):
            print(f"⚠️  Arquivo de música de fundo não encontrado: {video_config['background_music_file']}")
            print("⏭️  Pulando música de fundo...")
            has_bg_music = False
        else:
            cfg.set_item("background_music_file", video_config["background_music_file"])
            print(f"🎵 Música de fundo: {cfg.background_music_file}")

    # --- 4. Gerar vídeo de fundo ---
    print("🎥 Gerando vídeo de fundo...")
    cfg.set_item("enable_crossfade", False)
    bg = BackgroundVideo(cfg.config)
    final_video = bg.generate_background_video()
    
    if not final_video:
        raise RuntimeError("Nenhum vídeo de fundo foi gerado.")
    
    final_video = final_video.set_audio(audio_narration)
    final_video = final_video.resize(cfg.resolution_output)

    # --- 5. Verificar se há headline e gerar se necessário ---
    has_headline = "headline" in video_config and video_config["headline"]
    
    if has_headline:
        print("📰 Gerando headline...")
        headline_config = video_config["headline"]
        
        # output_path slug.png
        headline = Headline({
            "output_path": f"{video_config['slug']}.png",
            "title": headline_config.get("title", ""),
            "subtitle": headline_config.get("subtitle", ""),
            "video_width": cfg.width
        })
        headline_data = headline.generate()
        
        headline_clip = (
            ImageClip(headline_data["path"])
            .set_duration(cfg.max_total_video_duration)
            .set_opacity(cfg.manchete_opacity)
        )
    else:
        print("ℹ️  Sem headline - gerando apenas com legendas")
        headline_clip = None

    # --- 6. Gerar legendas ---
    print("📝 Gerando legendas...")
    sub = Subtitle(cfg.config)
    subtitle_clips = sub.generate()
    subtitle_clips = subtitle_clips.set_duration(cfg.max_total_video_duration)

    # --- 7. Montar o bloco (headline + legendas ou apenas legendas) ---
    GAP = 200
    
    if has_headline:
        # Com headline: redimensiona legendas para a largura da headline
        subtitle_clips = subtitle_clips.resize(width=headline_clip.w)
        
        block = CompositeVideoClip([
            headline_clip,
            subtitle_clips.set_position(("center", headline_clip.h + GAP))
        ], size=(headline_clip.w, headline_clip.h + subtitle_clips.h + GAP))
        
        block = block.resize(width=int(cfg.width * 0.8))
    else:
        # Sem headline: legendas sozinhas
        subtitle_clips = subtitle_clips.resize(width=int(cfg.width * 0.8))
        block = subtitle_clips

    # --- 8. Composição final ---
    print("🎨 Montando composição final...")
    final = CompositeVideoClip([
        final_video,
        block.set_position(("center", int(final_video.h * 0.3 - block.h / 2)))
    ])

    # --- 9. Renderização ---
    os.makedirs(output_folder, exist_ok=True)
    
    safe_title = video_config["title"][:50].replace(" ", "_").replace(":", "").replace("🚀", "").replace("🤖", "").lower()
    safe_title = "".join(c for c in safe_title if c.isalnum() or c == "_")
    
    output_file = os.path.join(
        output_folder, 
        f"{safe_title}_{cfg.output_ratio.replace(':', '_')}.mp4"
    )

    print(f"💾 Renderizando vídeo: {output_file}")
    final.write_videofile(
        output_file,
        codec="libx264",
        audio_codec="aac",
        fps=25,
        threads=5,
        temp_audiofile="temp-audio.m4a",
        remove_temp=True,
        bitrate="3000k",
        preset="superfast",
    )

    print(f"✅ Vídeo salvo com sucesso!")
    
    # Salvar metadados do vídeo (description, hashtags)
    metadata_file = output_file.replace(".mp4", "_metadata.txt")
    with open(metadata_file, "w", encoding="utf-8") as f:
        f.write(f"TÍTULO:\n{video_config['title']}\n\n")
        f.write(f"DESCRIÇÃO:\n{video_config['description']}\n\n")
        if "hashtags" in video_config:
            f.write(f"HASHTAGS:\n{video_config['hashtags']}\n")
    
    print(f"📄 Metadados salvos: {metadata_file}")


def main():
    """Função principal que processa todos os vídeos do JSON."""
    print("\n" + "="*60)
    print("🎬 GERADOR DE VÍDEOS AUTOMATIZADO")
    print("="*60)
    
    start_time = time.time()
    
    # Caminho do arquivo JSON
    json_file = "videos_config.json"
    
    if not os.path.exists(json_file):
        print(f"❌ Erro: Arquivo {json_file} não encontrado!")
        print("💡 Crie um arquivo 'videos_config.json' com suas configurações.")
        return
    
    # Carregar configurações
    print(f"\n📂 Carregando configurações de: {json_file}")
    with open(json_file, "r", encoding="utf-8") as f:
        videos_config = json.load(f)
    
    if not isinstance(videos_config, list):
        print("❌ Erro: O JSON deve conter uma lista de vídeos!")
        return
    
    print(f"✅ {len(videos_config)} vídeo(s) encontrado(s)")
    
    # Criar pasta de saída principal
    output_base = "output"
    os.makedirs(output_base, exist_ok=True)
    
    # Processar cada vídeo
    success_count = 0
    error_count = 0
    
    for index, video_config in enumerate(videos_config, 1):
        try:
            print(f"\n{'='*60}")
            print(f"📹 VÍDEO {index}/{len(videos_config)}")
            print(f"{'='*60}")
            
            # Validar campos obrigatórios
            required_fields = ["slug", "title", "description", "narration_text", "background_videos_dir"]
            missing_fields = [f for f in required_fields if f not in video_config]
            
            if missing_fields:
                print(f"⚠️  Campos obrigatórios ausentes: {', '.join(missing_fields)}")
                print("⏭️  Pulando para o próximo vídeo...")
                error_count += 1
                continue
            
            # Verificar se diretório de vídeos existe
            if not os.path.exists(video_config["background_videos_dir"]):
                print(f"⚠️  Diretório não encontrado: {video_config['background_videos_dir']}")
                print("⏭️  Pulando para o próximo vídeo...")
                error_count += 1
                continue
            
            # Criar configuração
            cfg = Config()
            
            # Processar vídeo
            process_video(cfg, video_config, output_base)
            success_count += 1
            
        except Exception as e:
            print(f"\n❌ ERRO ao processar vídeo {index}: {e}")
            import traceback
            traceback.print_exc()
            error_count += 1
            continue
    
    # Resumo final
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    print("\n" + "="*60)
    print("🏁 PROCESSAMENTO CONCLUÍDO")
    print("="*60)
    print(f"✅ Vídeos gerados com sucesso: {success_count}")
    print(f"❌ Vídeos com erro: {error_count}")
    print(f"⏱️  Tempo total: {elapsed_time:.2f}s ({elapsed_time/60:.1f} minutos)")
    print("="*60)


if __name__ == "__main__":
    main()