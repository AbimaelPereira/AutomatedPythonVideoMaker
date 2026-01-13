"""
AssetManager - Serviço responsável por gerenciar backgrounds, IA e cache de assets.

Este serviço encapsula toda a lógica relacionada a:
- Criação de backgrounds (cor, imagem, vídeo, diretório de vídeos)
- Geração de backgrounds usando IA (Pollinations, etc.)
- Gerenciamento de cache de vídeos de background
- Seleção aleatória de vídeos sem repetição
- Cache de assets gerados por IA

Preserva o comportamento exato do UnifiedVideoEngine original em termos de:
- Políticas de duração e loop de vídeos
- Crossfade entre vídeos
- Histórico de não repetição de vídeos
- Fallback para fundo preto em caso de erro
"""

import os
import random
import hashlib
import json
from moviepy.editor import (
    ColorClip, ImageClip, VideoFileClip, 
    concatenate_videoclips
)

from libs.BackgroundVideo import BackgroundVideo
from libs.MediaDownloader import MediaDownloader

try:
    from libs.AIProviders import ai_manager
    from libs.AIProviders.AICache import AICache
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    ai_manager = None
    AICache = None


def hex_to_rgb(hex_value):
    """Converte cor hexadecimal para tupla RGB"""
    if not isinstance(hex_value, str):
        return hex_value
    hex_value = hex_value.lstrip('#')
    try:
        if len(hex_value) == 6:
            return tuple(int(hex_value[i:i+2], 16) for i in (0, 2, 4))
        else:
            return (0, 0, 0)
    except ValueError:
        return (0, 0, 0)


class AssetManager:
    """
    Gerenciador de assets de background e IA.
    
    Responsável por criar e gerenciar todos os tipos de backgrounds,
    incluindo geração via IA e cache de assets.
    """
    
    def __init__(self, resolution_output=(1080, 1920), global_settings=None):
        """
        Inicializa o gerenciador de assets.
        
        Args:
            resolution_output: Tupla (width, height) para resolução do vídeo
            global_settings: Configurações globais (crossfade, etc.)
        """
        self.resolution_output = resolution_output
        self.global_settings = global_settings or {}
        
        # Cache de vídeos de background por diretório
        self.bg_cache = {}
        
        # Histórico de vídeos usados recentemente (para evitar repetição)
        self.last_used_videos = []
        self.max_history = 3
        
        # Cache de IA
        if AI_AVAILABLE:
            cache_dir = os.path.join(os.getcwd(), "cache", "ai_generated")
            self.ai_cache = AICache(cache_dir)
        else:
            self.ai_cache = None
    
    def create_background(self, background_config, scene_duration, storage_dir):
        """
        Cria clip de background baseado na configuração.
        
        Args:
            background_config: Dicionário com configuração de background
            scene_duration: Duração da cena em segundos
            storage_dir: Diretório para armazenar assets temporários
        
        Returns:
            Clip de background (ColorClip, ImageClip ou VideoClip)
        """
        print(f"[AssetManager] Criando fundo para duração: {scene_duration:.2f}s")
        
        visual_config = background_config.get("visual", {})
        bg_type = visual_config.get("type", "color")
        bg_clip = None
        
        try:
            if bg_type == "color":
                bg_clip = self._create_color_background(visual_config, scene_duration)
            
            elif bg_type == "image":
                bg_clip = self._create_image_background(visual_config, scene_duration, storage_dir)
            
            elif bg_type == "video":
                bg_clip = self._create_video_background(visual_config, scene_duration, storage_dir)
            
            elif bg_type == "ai":
                bg_clip = self._create_ai_background(visual_config, scene_duration, storage_dir)
            
            elif bg_type == "directory":
                bg_clip = self._create_directory_background(visual_config, scene_duration)
            
            else:
                print(f"[AssetManager] ⚠️ Tipo de fundo desconhecido: {bg_type}, usando preto")
                bg_clip = ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
        
        except Exception as e:
            print(f"[AssetManager] ❌ Falha ao criar fundo: {e}")
            import traceback
            traceback.print_exc()
            print(f"[AssetManager] Usando fundo preto como fallback")
            bg_clip = ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
        
        return bg_clip
    
    def _create_color_background(self, visual_config, scene_duration):
        """Cria background de cor sólida."""
        color = visual_config.get("source", "#000000")
        if isinstance(color, str):
            color = hex_to_rgb(color)
        print(f"[AssetManager] Criando fundo colorido: {color}")
        return ColorClip(size=self.resolution_output, color=color).set_duration(scene_duration)
    
    def _create_image_background(self, visual_config, scene_duration, storage_dir):
        """Cria background de imagem."""
        src = visual_config.get("source")
        if not src:
            raise ValueError("Source da imagem não especificada")
        
        path = MediaDownloader.resolve_source_path(src, storage_dir)
        print(f"[AssetManager] Carregando imagem de fundo: {path}")
        
        return (ImageClip(path)
                .resize(newsize=self.resolution_output)
                .set_duration(scene_duration))
    
    def _create_video_background(self, visual_config, scene_duration, storage_dir):
        """Cria background de vídeo único."""
        src = visual_config.get("source")
        if not src:
            raise ValueError("Source do vídeo não especificada")
        
        path = MediaDownloader.resolve_source_path(src, storage_dir)
        print(f"[AssetManager] Carregando vídeo de fundo: {path}")
        
        bg_clip = VideoFileClip(path, audio=False)
        bg_clip = bg_clip.resize(newsize=self.resolution_output)
        
        if bg_clip.duration < scene_duration:
            bg_clip = bg_clip.loop(duration=scene_duration)
        else:
            bg_clip = bg_clip.subclip(0, scene_duration)
        
        return bg_clip.without_audio()
    
    def _create_ai_background(self, visual_config, scene_duration, storage_dir):
        """Cria background usando IA."""
        if not AI_AVAILABLE or not self.ai_cache:
            raise ValueError("Sistema de IA não está disponível")
        
        try:
            provider = visual_config.get("provider", "pollinations")
            content_type = visual_config.get("content_type", "image")
            prompt = visual_config.get("prompt", "")
            parameters = visual_config.get("parameters", {})
            cache_key = visual_config.get("cache_key")
            
            if not prompt:
                raise ValueError("Prompt não especificado para IA background")
            
            print(f"[AssetManager] 🤖 Processando background IA: {content_type}")
            print(f"[AssetManager] Prompt: {prompt[:100]}...")
            
            # Gerar cache key se não fornecido
            if not cache_key:
                cache_data = {
                    "provider": provider,
                    "type": content_type,
                    "prompt": prompt,
                    "parameters": parameters
                }
                cache_key = hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()[:12]
                print(f"[AssetManager] Cache key gerado: {cache_key}")
            
            # Verificar cache
            cached_file = self.ai_cache.get(cache_key, content_type)
            if cached_file:
                print(f"[AssetManager] ✅ IA background encontrado no cache: {os.path.basename(cached_file)}")
                file_path = cached_file
            else:
                # Gerar novo
                print(f"[AssetManager] 🎨 Gerando {content_type} background com {provider}...")
                
                if not parameters.get("width") and not parameters.get("height"):
                    parameters["width"] = self.resolution_output[0]
                    parameters["height"] = self.resolution_output[1]
                
                if content_type == "image":
                    result = ai_manager.generate_image(prompt=prompt, provider=provider, **parameters)
                elif content_type == "video":
                    result = ai_manager.generate_video(prompt=prompt, provider=provider, **parameters)
                else:
                    raise ValueError(f"Tipo de conteúdo IA inválido: {content_type}")
                
                if not result.get("success"):
                    raise ValueError(f"Falha na geração IA: {result.get('error')}")
                
                extension = "png" if content_type == "image" else "mp4"
                filename = f"ai_bg_{cache_key}.{extension}"
                file_path = os.path.join(storage_dir, filename)
                
                with open(file_path, "wb") as f:
                    f.write(result["content"])
                
                print(f"[AssetManager] ✅ IA background salvo: {filename} ({result['size']} bytes)")
                
                self.ai_cache.store(cache_key, file_path, content_type, {
                    "prompt": prompt,
                    "provider": provider,
                    "parameters": parameters,
                    "size": result["size"]
                })
            
            # Criar clip
            if content_type == "image":
                bg_clip = (ImageClip(file_path)
                          .resize(newsize=self.resolution_output)
                          .set_duration(scene_duration))
                print(f"[AssetManager] ✅ IA background (imagem) criado: {scene_duration:.2f}s")
            
            elif content_type == "video":
                bg_clip = VideoFileClip(file_path, audio=False)
                bg_clip = bg_clip.resize(newsize=self.resolution_output)
                
                if bg_clip.duration < scene_duration:
                    bg_clip = bg_clip.loop(duration=scene_duration)
                else:
                    bg_clip = bg_clip.subclip(0, scene_duration)
                
                bg_clip = bg_clip.without_audio()
                print(f"[AssetManager] ✅ IA background (vídeo) criado: {scene_duration:.2f}s")
            
            return bg_clip
        
        except Exception as e:
            print(f"[AssetManager] ❌ Erro ao criar IA background: {e}")
            import traceback
            traceback.print_exc()
            return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
    
    def _create_directory_background(self, visual_config, scene_duration):
        """Cria background de diretório de vídeos."""
        source_dir = visual_config.get("source")
        if not source_dir:
            raise ValueError("Diretório source não especificado")
        
        print(f"[AssetManager] Processando vídeos do diretório: {source_dir}")
        
        # Carregar ou obter do cache
        if source_dir not in self.bg_cache:
            print(f"[AssetManager] Carregando vídeos do diretório para cache...")
            loader = BackgroundVideo({
                "background_videos_dir": source_dir,
                "resolution_output": self.resolution_output,
                "output_ratio": self.global_settings.get("output_ratio", "9:16"),
                "crossfade_duration": self.global_settings.get("crossfade_duration", 0.8),
                "enable_crossfade": self.global_settings.get("enable_crossfade", True),
                "shuffle_clips": self.global_settings.get("shuffle_clips", True),
                "loop_background": self.global_settings.get("loop_background", True),
                "max_clips": self.global_settings.get("max_clips")
            })
            
            if hasattr(loader, "get_all_processed_clips"):
                self.bg_cache[source_dir] = loader.get_all_processed_clips()
            elif hasattr(loader, "get_processed_clips"):
                self.bg_cache[source_dir] = loader.get_processed_clips()
            else:
                print("[AssetManager] ⚠️ BackgroundVideo não tem método de cache conhecido")
                self.bg_cache[source_dir] = []
        
        cached_clips = self.bg_cache.get(source_dir, [])
        if not cached_clips:
            print("[AssetManager] ⚠️ Cache vazio, usando fundo preto")
            return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
        
        print(f"[AssetManager] Cache contém {len(cached_clips)} vídeos processados")
        
        # Selecionar vídeos para a duração
        selected_clips = self._select_random_videos_for_duration(cached_clips, scene_duration)
        
        if not selected_clips:
            print("[AssetManager] ⚠️ Nenhum vídeo selecionado, usando fundo preto")
            return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
        
        # Compor clips
        if len(selected_clips) == 1:
            bg_clip = selected_clips[0]
            if bg_clip.duration < scene_duration:
                bg_clip = bg_clip.loop(duration=scene_duration)
            elif bg_clip.duration > scene_duration:
                bg_clip = bg_clip.subclip(0, scene_duration)
        else:
            print(f"[AssetManager] Concatenando {len(selected_clips)} vídeos para o fundo")
            
            enable_crossfade = self.global_settings.get("enable_crossfade", False)
            crossfade_duration = self.global_settings.get("crossfade_duration", 0.5)
            
            if enable_crossfade and len(selected_clips) > 1:
                bg_clip = selected_clips[0]
                for next_clip in selected_clips[1:]:
                    bg_clip = concatenate_videoclips([bg_clip, next_clip], method="compose")
                    if bg_clip.duration > crossfade_duration:
                        bg_clip = bg_clip.crossfadein(crossfade_duration)
            else:
                bg_clip = concatenate_videoclips(selected_clips, method="compose")
            
            # Ajustar duração final
            if bg_clip.duration > scene_duration:
                bg_clip = bg_clip.subclip(0, scene_duration)
            elif bg_clip.duration < scene_duration:
                remaining = scene_duration - bg_clip.duration
                if remaining > 0 and selected_clips:
                    last_clip = selected_clips[-1]
                    if last_clip.duration >= remaining:
                        extra_clip = last_clip.subclip(0, remaining)
                    else:
                        extra_clip = last_clip.loop(duration=remaining)
                    bg_clip = concatenate_videoclips([bg_clip, extra_clip])
        
        print(f"[AssetManager] ✅ Fundo criado com duração final: {bg_clip.duration:.2f}s")
        return bg_clip
    
    def _select_random_videos_for_duration(self, available_clips, target_duration):
        """
        Seleciona vídeos aleatórios para cobrir a duração necessária,
        evitando repetir vídeos usados recentemente.
        
        Args:
            available_clips: Lista de clips disponíveis
            target_duration: Duração alvo em segundos
        
        Returns:
            Lista de clips selecionados
        """
        if not available_clips:
            return []
        
        selected_clips = []
        current_duration = 0.0
        attempts = 0
        max_attempts = len(available_clips) * 3
        
        # Filtrar clips já usados recentemente
        available_for_selection = []
        for clip in available_clips:
            clip_path = getattr(clip, 'filename', str(hash(str(clip))))
            if clip_path not in self.last_used_videos:
                available_for_selection.append(clip)
        
        # Reset histórico se todos já foram usados
        if not available_for_selection:
            print(f"[AssetManager] Resetando histórico de vídeos para evitar deadlock")
            available_for_selection = available_clips.copy()
            self.last_used_videos = []
        
        print(f"[AssetManager] Selecionando vídeos para duração: {target_duration:.2f}s")
        print(f"[AssetManager] Vídeos disponíveis: {len(available_for_selection)} (histórico: {len(self.last_used_videos)})")
        
        while current_duration < target_duration and attempts < max_attempts:
            attempts += 1
            
            if not available_for_selection:
                break
            
            selected_clip = random.choice(available_for_selection)
            clip_duration = getattr(selected_clip, 'duration', 4.0)
            
            remaining_duration = target_duration - current_duration
            actual_duration = min(clip_duration, remaining_duration)
            
            if actual_duration < clip_duration:
                start_time = random.uniform(0, max(0, clip_duration - actual_duration))
                clip_segment = selected_clip.subclip(start_time, start_time + actual_duration)
            else:
                clip_segment = selected_clip.copy()
            
            selected_clips.append(clip_segment)
            current_duration += actual_duration
            
            clip_path = getattr(selected_clip, 'filename', str(hash(str(selected_clip))))
            if clip_path not in self.last_used_videos:
                self.last_used_videos.append(clip_path)
            
            available_for_selection.remove(selected_clip)
            
            print(f"[AssetManager] Vídeo selecionado: duração {actual_duration:.2f}s (total: {current_duration:.2f}s)")
            
            if not available_for_selection and current_duration < target_duration:
                print(f"[AssetManager] ⚠️ Acabaram os vídeos únicos. Duração atual: {current_duration:.2f}s")
                break
        
        # Manter histórico limitado
        if len(self.last_used_videos) > self.max_history:
            self.last_used_videos = self.last_used_videos[-self.max_history:]
        
        print(f"[AssetManager] ✅ {len(selected_clips)} vídeos selecionados para duração total: {current_duration:.2f}s")
        return selected_clips
