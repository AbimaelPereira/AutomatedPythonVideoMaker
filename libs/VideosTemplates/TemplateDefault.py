import os
import shutil
from libs.TemplateMaster import TemplateMaster
from libs.YouTube import YouTube
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
                f"{slug}_{self.video_config['output_ratio'].replace(':', '_')}.mp4"
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
                video_id = self.tm.upload_to_youtube({
                    "video_path": output_file,
                    "content": self.video_config.get("content", {}),
                    "youtube": self.video_config["youtube"],
                    "tts": self.video_config.get("tts", {}),
                    "remove_project_folder": True  # Remove pasta após upload bem-sucedido
                })
                
                if not video_id:
                    print("⚠️  Upload falhou, mas o vídeo foi salvo localmente.")
            
            return True
            
        except Exception as e:
            print(f"\n❌ ERRO ao processar vídeo: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _upload_to_youtube(self, video_path, project_folder):
        """
        Faz upload do vídeo para o YouTube.
        
        Args:
            video_path: Caminho do arquivo de vídeo
            project_folder: Pasta do projeto (será removida após upload)
        """
        try:
            yt_config = self.video_config["youtube"]
            
            print("\n🚀 Iniciando upload para o YouTube...")
            
            # Montar título
            title = self.video_config["content"]["title"][:100]
            
            # Montar descrição
            description_parts = []
            if self.video_config["content"].get("description"):
                description_parts.append(self.video_config["content"]["description"])
            if self.video_config["tts"].get("narration_text"):
                description_parts.append("\n\n" + self.video_config["tts"]["narration_text"])
            if self.video_config["content"].get("hashtags"):
                description_parts.append("\n\n" + self.video_config["content"]["hashtags"])
            description = "".join(description_parts).strip()[:5000]
            
            # Processar tags
            tags = []
            if self.video_config["content"].get("hashtags"):
                tags = [tag.replace("#", "").strip() 
                       for tag in self.video_config["content"]["hashtags"].split() 
                       if tag.strip()]
                tags_str = ",".join(tags)
                if len(tags_str) > 500:
                    tags = tags_str[:500].split(",")[:-1]
            
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
                "video_path": video_path,
                "title": title,
                "description": description,
                "tags": tags,
                "privacy_status": privacy_status,
                "category_id": yt_config.get("category_id", "22"),
                "publish_at": publish_at,
                "pinned_comment": yt_config.get("pinned_comment", False)
            })
            
            # Fazer upload
            print(f"🎬 Título: {title}")
            print(f"🏷️ Tags: {', '.join(tags[:5])}{'...' if len(tags) > 5 else ''}")
            print(f"🔒 Privacidade: {privacy_status}")
            
            video_id = yt.upload()
            print(f"✅ Upload concluído com sucesso!")
            print(f"🔗 Link do vídeo: https://youtu.be/{video_id}")
            
            # Remover pasta do projeto após upload
            shutil.rmtree(project_folder)
            print(f"🗑️ Pasta do projeto removida: {project_folder}")
            
        except Exception as e:
            print(f"\n❌ ERRO no upload para YouTube: {e}")
            import traceback
            traceback.print_exc()
            print("⚠️ O vídeo foi gerado, mas o upload falhou.")