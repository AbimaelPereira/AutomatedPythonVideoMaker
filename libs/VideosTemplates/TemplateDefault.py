import os
from libs.TemplateMaster import TemplateMaster
from moviepy.editor import CompositeVideoClip, CompositeAudioClip


class TemplateDefault:
    def __init__(self, video_config):
        """
        Inicializa o template com as configurações do vídeo.
        
        Args:
            video_config: Dicionário com todas as configurações do vídeo
        """
        self.video_config = video_config
        self.tm = None
        
    def validate_configs(self):
        """
        Valida as configurações necessárias para o template.
        Retorna uma lista de erros encontrados.
        """
        errors = []
        
        # Validações obrigatórias
        if not self.video_config.get("slug"):
            errors.append("'slug' é obrigatório")
            
        if not self.video_config.get("output_ratio"):
            errors.append("'output_ratio' é obrigatório")
            
        if not self.video_config.get("tts"):
            errors.append("'tts' é obrigatório")
        elif not self.video_config["tts"].get("narration_text"):
            errors.append("'tts.narration_text' é obrigatório")
            
        if not self.video_config.get("background"):
            errors.append("'background' é obrigatório")
        elif not self.video_config["background"].get("videos_dir"):
            errors.append("'background.videos_dir' é obrigatório")
        elif not os.path.exists(self.video_config["background"]["videos_dir"]):
            errors.append(f"Diretório de vídeos não encontrado: {self.video_config['background']['videos_dir']}")
            
        if not self.video_config.get("content"):
            errors.append("'content' é obrigatório")
        elif not self.video_config["content"].get("title"):
            errors.append("'content.title' é obrigatório")
            
        return errors
    
    def process(self):
        """
        Processa o vídeo completo seguindo o template.
        Retorna True se sucesso, False se erro.
        """
        try:
            slug = self.video_config["slug"]
            output_folder = f"output/{slug}"
            
            print(f"\n🎬 Gerando vídeo: {self.video_config['content']['title'][:50]}...")
            print(f"📐 Proporção: {self.video_config['output_ratio']}")
            
            # Criar pasta de saída
            os.makedirs(output_folder, exist_ok=True)
            print(f"📁 Pasta do projeto: {output_folder}")
            
            # Inicializar TemplateMaster
            self.tm = TemplateMaster({
                "slug": slug,
                "output_folder": output_folder,
                "output_ratio": self.video_config["output_ratio"],
            })
            
            # 1. Gerar narração e legendas
            print("🎙️ Gerando narração e legendas...")
            narration_result = self.tm.narration_subtitles(self.video_config["tts"])
            audio_narration = narration_result["audio_narration"]
            subtitle_clips = narration_result["subtitle_clips"]
            
            # Definir duração total
            self.tm.max_total_video_duration = audio_narration.duration
            print(f"⏱️ Duração do áudio: {audio_narration.duration:.2f}s")
            
            # 2. Gerar vídeo de fundo
            print("🎥 Gerando vídeo de fundo...")
            background_video = self.tm.background_videos({
                "background_videos_dir": self.video_config["background"]["videos_dir"]
            })
            
            # 3. Processar música de fundo (opcional)
            final_audio = audio_narration
            if self.video_config["background"].get("music_dir"):
                print("🎵 Adicionando música de fundo...")
                bg_music = self.tm.background_music({
                    "background_music_dir": self.video_config["background"]["music_dir"]
                })
                
                if bg_music:
                    # Reduzir volume da música para 25%
                    bg_music = bg_music.volumex(0.25)
                    final_audio = CompositeAudioClip([bg_music, audio_narration])
                    print("🔊 Áudio mixado com música de fundo")
            
            # Adicionar áudio ao vídeo de fundo
            background_video = background_video.set_audio(final_audio)
            
            # 4. Gerar headline (opcional)
            block = None
            if self.video_config.get("headline") and self.video_config["headline"]:
                print("📰 Gerando headline...")
                headline_clip = self.tm.headline({
                    "title": self.video_config["content"]["title"],
                    "subtitle": self.video_config["headline"].get("subtitle", "")
                })
                
                # Redimensionar legendas para a largura da headline
                subtitle_clips_resized = subtitle_clips.resize(width=headline_clip.w)
                
                GAP = 200
                
                # Criar bloco com headline + legendas
                block = CompositeVideoClip([
                    headline_clip,
                    subtitle_clips_resized.set_position(("center", headline_clip.h + GAP))
                ], size=(headline_clip.w, headline_clip.h + subtitle_clips_resized.h + GAP))
                
                # Redimensionar bloco para 80% da largura do vídeo
                block = block.resize(width=int(self.tm.width * 0.8))
            else:
                # Apenas legendas, sem headline
                print("ℹ️ Sem headline - gerando apenas com legendas")
                block = subtitle_clips.resize(width=int(self.tm.width * 0.8))
            
            # 5. Composição final
            print("🎨 Montando composição final...")
            final = CompositeVideoClip([
                background_video,
                block.set_position(("center", int(background_video.h * 0.3 - block.h / 2)))
            ])
            
            # 6. Renderização
            output_file = os.path.join(
                output_folder,
                f"{slug}.mp4"
            )
            
            print(f"💾 Renderizando vídeo: {output_file}")
            final.write_videofile(
                output_file,
                codec="libx264",
                audio_codec="aac",
                fps=24,
                threads=5,
                temp_audiofile=os.path.join(output_folder, "temp-audio.m4a"),
                remove_temp=True,
                bitrate="4000k",
                preset="superfast",
            )
            
            print("✅ Vídeo salvo com sucesso!")
            
            # 7. Upload para YouTube (opcional)
            if self.video_config.get("youtube"):
                print("\n📤 Preparando upload para YouTube...")
                
                video_id = self.tm.upload_to_youtube({
                    "video_path": output_file,
                    "content": self.video_config.get("content", {}),
                    "youtube": self.video_config["youtube"],
                    "tts": self.video_config.get("tts", {}),
                    "remove_project_folder": self.video_config["youtube"].get("remove_project_folder", False)
                })
                
                if not video_id:
                    print("⚠️ Upload falhou, mas o vídeo foi salvo localmente.")
                    return False
            
            return True
            
        except Exception as e:
            print(f"\n❌ ERRO ao processar vídeo: {e}")
            import traceback
            traceback.print_exc()
            return False