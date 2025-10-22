import os
import json
import random
import shutil
import time
from moviepy.editor import CompositeVideoClip, AudioFileClip, ImageClip, CompositeAudioClip

from libs.Config import Config
from libs.TTS_Edge import EdgeTTS
from libs.BackgroundVideo import BackgroundVideo
from libs.Subtitle import Subtitle
from libs.Headline import Headline
from libs.YouTube import YouTube


def process_video(cfg: Config, video_config: dict, output_folder: str):
    """
    Processa um único vídeo com base na configuração fornecida.
    
    Args:
        cfg: Objeto de configuração
        video_config: Dicionário com as configurações do vídeo
        output_folder: Pasta base onde o vídeo será salvo
    """
    print(f"\n🎬 Gerando vídeo: {video_config['title'][:50]}...")
    print(f"📐 Proporção: {video_config.get('output_ratio', '9:16')}")

    # --- 1. Criar pasta do projeto usando o slug ---
    slug = video_config.get("slug", "video_sem_slug")
    project_folder = os.path.join(output_folder, slug)
    os.makedirs(project_folder, exist_ok=True)
    print(f"📁 Pasta do projeto: {project_folder}")

    # --- 2. Configurar diretório de vídeos de fundo ---
    cfg.set_item("background_videos_dir", video_config["background_videos_dir"])
    cfg.set_item("output_ratio", video_config.get("output_ratio", "9:16"))

    # --- 3. Gerar áudio e legenda com Edge TTS ---
    edge_tts_config = video_config.get("edge_tts", {})
    voice_id = edge_tts_config.get("voice_id", "pt-BR-AntonioNeural")
    
    print(f"🗣️  Gerando áudio com voz: {voice_id}")
    
    # Mudar diretório temporariamente para gerar arquivos na pasta correta
    original_dir = os.getcwd()
    os.chdir(project_folder)
    
    tts = EdgeTTS({
        "text": video_config["narration_text"],
        "voice_id": voice_id,
        "output_basename": slug,
    })
    tts_result = tts.generate_audio_and_subtitles()
    
    # Voltar para o diretório original
    os.chdir(original_dir)
    
    # Ajustar caminhos para absolutos
    audio_path = os.path.join(project_folder, tts_result["audio_file"])
    subtitle_path = os.path.join(project_folder, tts_result["subtitle_file"])
    
    cfg.set_item("audio_narration_file", audio_path)
    cfg.set_item("subtitle_narration_file", subtitle_path)
    
    print(f"🎵 Áudio salvo: {audio_path}")
    print(f"📝 Legenda salva: {subtitle_path}")

    # --- 4. Carregar áudio de narração e definir duração do vídeo ---
    audio_narration = AudioFileClip(cfg.audio_narration_file)
    cfg.set_item("max_total_video_duration", audio_narration.duration)
    print(f"⏱️  Duração do áudio: {audio_narration.duration:.2f}s")

    # --- 5. Verificar e processar música de fundo (opcional) ---
    has_bg_music = "background_music_dir" in video_config and video_config["background_music_dir"]
    bg_music_clip = None
    
    if has_bg_music:
        # pasta de musicas
        bg_music_dir = video_config["background_music_dir"]
        if not os.path.exists(bg_music_dir):
            print(f"⚠️  Diretório de música de fundo não encontrado: {bg_music_dir}")
            print("ℹ️  Continuando sem música de fundo.")
            has_bg_music = False
        else:
            print(f"🎵 Selecionando música de fundo da pasta: {bg_music_dir}")

            # escolher uma música aleatória da pasta
            music_files = [f for f in os.listdir(bg_music_dir) if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac'))]
            if not music_files:
                print(f"⚠️  Nenhum arquivo de música encontrado em: {bg_music_dir}")
                print("ℹ️  Continuando sem música de fundo.")
                has_bg_music = False
            else:
                selected_music = random.choice(music_files)
                bg_music_path = os.path.join(bg_music_dir, selected_music)
                print(f"🎶 Música selecionada: {selected_music}")
                
                # Carregar música de fundo
            bg_music_clip = AudioFileClip(bg_music_path)
            
            # Ajustar duração da música de fundo para a duração da narração
            if bg_music_clip.duration < cfg.max_total_video_duration:
                # Loop da música se for muito curta
                n_loops = int(cfg.max_total_video_duration // bg_music_clip.duration) + 1
                print(f"🔁 Repetindo música de fundo {n_loops}x para cobrir toda a duração")
                bg_music_clip = CompositeAudioClip([bg_music_clip] * n_loops)
            
            # Cortar música para a duração exata
            bg_music_clip = bg_music_clip.subclip(0, cfg.max_total_video_duration)

            # Reduzir volume para 35%
            bg_music_clip = bg_music_clip.volumex(0.35)
            print(f"🔊 Volume da música de fundo ajustado para 35%")

    # --- 6. Gerar vídeo de fundo ---
    print("🎥 Gerando vídeo de fundo...")
    cfg.set_item("enable_crossfade", False)
    bg = BackgroundVideo(cfg.config)
    final_video = bg.generate_background_video()
    
    if not final_video:
        raise RuntimeError("Nenhum vídeo de fundo foi gerado.")
    
    # --- 7. Mixar áudios (narração + música de fundo se houver) ---
    if has_bg_music and bg_music_clip:
        print("🎚️  Mixando narração com música de fundo...")
        final_audio = CompositeAudioClip([bg_music_clip, audio_narration])
        final_video = final_video.set_audio(final_audio)
    else:
        final_video = final_video.set_audio(audio_narration)
    
    final_video = final_video.resize(cfg.resolution_output).set_duration(cfg.max_total_video_duration)

    # --- 8. Verificar se há headline e gerar se necessário ---
    has_headline = "headline" in video_config and video_config["headline"]
    
    if has_headline:
        print("📰 Gerando headline...")
        headline_config = video_config["headline"]
        
        headline_path = os.path.join(project_folder, "headline.png")
        
        headline = Headline({
            "output_path": headline_path,
            "title": headline_config.get("title", ""),
            "subtitle": headline_config.get("subtitle", ""),
            "video_width": cfg.width
        })
        headline_data = headline.generate()
        print(f"🖼️  Headline salva: {headline_path}")
        
        headline_clip = (
            ImageClip(headline_data["path"])
            .set_duration(cfg.max_total_video_duration)
            .set_opacity(cfg.manchete_opacity)
        )
    else:
        print("ℹ️  Sem headline - gerando apenas com legendas")
        headline_clip = None

    # --- 9. Gerar legendas ---
    print("📝 Gerando legendas...")
    sub = Subtitle(cfg.config)
    subtitle_clips = sub.generate()
    subtitle_clips = subtitle_clips.set_duration(cfg.max_total_video_duration)

    # --- 10. Montar o bloco (headline + legendas ou apenas legendas) ---
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

    # --- 11. Composição final ---
    print("🎨 Montando composição final...")
    final = CompositeVideoClip([
        final_video,
        block.set_position(("center", int(final_video.h * 0.3 - block.h / 2)))
    ])

    # --- 12. Renderização ---
    output_file = os.path.join(
        project_folder, 
        f"{slug}_{cfg.output_ratio.replace(':', '_')}.mp4"
    )

    print(f"💾 Renderizando vídeo: {output_file}")
    final.write_videofile(
        output_file,
        codec="libx264",
        audio_codec="aac",
        fps=24,
        threads=5,
        temp_audiofile=os.path.join(project_folder, "temp-audio.m4a"),
        remove_temp=True,
        bitrate="2000k",
        preset="superfast", # opções: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
    )

    print(f"✅ Vídeo salvo com sucesso!")
    
    # --- 13. Fazer upload Youtube ---
    if video_config.get("youtube"):
        try:
            yt_config = video_config.get("youtube", {})
            
            print("\n🚀 Iniciando upload para o YouTube...")

            # Montar título
            title = video_config["title"][:100]  # YouTube limita a 100 caracteres
            
            # Montar descrição
            description_parts = []
            if video_config.get("description"):
                description_parts.append(video_config["description"])
            if video_config.get("narration_text"):
                description_parts.append("\n\n" + video_config["narration_text"])
            if video_config.get("hashtags"):
                description_parts.append("\n\n" + video_config["hashtags"])
            description = "".join(description_parts).strip()[:5000]  # YouTube limita a 5000 caracteres

            # Processar tags (YouTube permite até 500 caracteres no total)
            tags = []
            if video_config.get("hashtags"):
                # Remove # e divide por espaço
                tags = [tag.replace("#", "").strip() 
                       for tag in video_config["hashtags"].split() 
                       if tag.strip()]
                # Limita a 500 caracteres no total
                tags_str = ",".join(tags)
                if len(tags_str) > 500:
                    tags = tags_str[:500].split(",")[:-1]  # Remove última tag incompleta

            # Configurar privacidade e agendamento
            privacy_status = "private"
            publish_at = None
            
            if yt_config.get("publish_at"):
                privacy_status = "private"
                publish_at = yt_config["publish_at"]
                print(f"⏰ Vídeo será agendado para: {publish_at}")
            elif yt_config.get("privacy_status"):
                privacy_status = yt_config["privacy_status"]
            
            # Criar instância do YouTube
            yt = YouTube({
                "token_file_name": yt_config.get("token_file_name", "youtube_token.json"),
                "video_path": output_file,
                "title": title,
                "description": description,
                "tags": tags,
                "privacy_status": privacy_status,
                "category_id": yt_config.get("category_id", "22"),  # 22 = People & Blogs
                "publish_at": publish_at,
                "pinned_comment": yt_config.get("pinned_comment", False)
            })
            
            # Configurar agendamento se fornecido
            if publish_at:
                yt.set_item("publish_at", publish_at)
            
            # Fazer upload
            print(f"📹 Título: {title}")
            print(f"🏷️  Tags: {', '.join(tags[:5])}{'...' if len(tags) > 5 else ''}")
            print(f"🔒 Privacidade: {privacy_status}")
            print(f"🕒 Agendamento: {publish_at}")
            
            video_id = yt.upload()
            print(f"✅ Upload concluído com sucesso!")
            print(f"🔗 Link do vídeo: https://youtu.be/{video_id}")


            # remover a pasta do projeto após o upload
            shutil.rmtree(project_folder)
            print(f"🗑️  Pasta do projeto removida: {project_folder}")
            
        except Exception as e:
            print(f"\n❌ ERRO no upload para YouTube: {e}")
            import traceback
            traceback.print_exc()
            print("⚠️  O vídeo foi gerado, mas o upload falhou.")

    print(f"\n🏁 Processo concluído para o vídeo: {video_config['title'][:50]}")


def main():
    """Função principal que processa todos os vídeos do JSON."""
    print("\n" + "="*60)
    print("🎬 GERADOR DE VÍDEOS AUTOMATIZADO")
    print("="*60)
    
    start_time = time.time()
    
    # Caminho do arquivo JSON
    # json_file = "temp_files/videos_config.json"

    #pedir ao usuario para informar o caminho do arquivo json, autocompleta
    json_file = input("📂 Informe o caminho do arquivo JSON de configuração (ex: videos_config.json): ").strip()
    
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