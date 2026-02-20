import os
import json
import hashlib
from typing import Dict, List, Tuple, Optional
from moviepy.editor import ColorClip, ImageClip, VideoFileClip, CompositeVideoClip, concatenate_videoclips
from libs.Config import Config
from libs.VisualClip import force_rgb
from libs.MediaDownloader import MediaDownloader
from libs.Background.DirectoryType import DirectoryType
from libs.Background.FiltersEngine import FiltersEngine
from PIL import Image, ImageFilter
import numpy as np

try:
    from libs.AIProviders import ai_manager
    from libs.AIProviders.AICache import AICache
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    ai_manager = None
    AICache = None


def _hex_to_rgb(hex_value):
    if not isinstance(hex_value, str):
        return tuple(hex_value)
    hex_value = hex_value.lstrip('#')
    try:
        if len(hex_value) == 6:
            return tuple(int(hex_value[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        pass
    return (0, 0, 0)


class BackgroundEngine:
    def __init__(self, resolution_output: Tuple[int, int], dir_clips_cache: Dict[str, List],
                 ai_cache=None, remote_asset_manager=None):
        self.resolution_output = tuple(map(int, resolution_output))
        self.dir_clips_cache = dir_clips_cache
        self.ai_cache = ai_cache if AI_AVAILABLE else None
        self.remote_asset_manager = remote_asset_manager  # NOVO
        self.last_used_videos: List[str] = []
        self.max_history = 3

    def _build_color(self, cfg: Dict, scene_duration: float):
        color = cfg.get("source", "#000000")
        if isinstance(color, str):
            color = _hex_to_rgb(color)
        return ColorClip(size=self.resolution_output, color=color).set_duration(scene_duration)

    def _create_blurred_background(self, image_path: str, scene_duration: float):
        pil_img = Image.open(image_path).convert("RGB")
        pil_img = pil_img.resize(self.resolution_output, Image.LANCZOS)
        pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=50))
        
        temp_blur_path = image_path.replace(".png", "_blur.png").replace(".jpg", "_blur.jpg")
        pil_img.save(temp_blur_path)
        
        clip = ImageClip(temp_blur_path).resize(newsize=self.resolution_output).set_duration(scene_duration)
        # CORREÇÃO: Força RGB
        return clip.fl_image(force_rgb)

    def _build_image(self, cfg: Dict, scene_duration: float, storage_dir: str):
        """
        MODIFICADO: Tenta todas as URLs disponíveis antes de usar fallback
        """
        src_type = cfg.get("type", "image")
        src = cfg.get("source")
        
        if src_type == "remote_asset":
            if not self.remote_asset_manager:
                print("[BackgroundEngine] ⚠️ RemoteAssetManager não disponível, usando cor sólida")
                return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
            
            slug = src
            if not slug:
                print("[BackgroundEngine] ❌ Slug não especificado, usando cor sólida")
                return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
            
            # NOVO: Loop tentando todas as URLs disponíveis
            attempt = 0
            while True:
                attempt += 1
                selected_url = self.remote_asset_manager.select_url(slug)
                
                if not selected_url:
                    print(f"[BackgroundEngine] ⚠️ Nenhuma URL válida restante no slug '{slug}', usando cor sólida")
                    return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
                
                src = selected_url
                print(f"[BackgroundEngine] 🎯 Tentativa {attempt}: {src[:50]}...")
                
                # Callbacks
                def on_success(url):
                    self.remote_asset_manager.mark_download_success(url)
                
                def on_fail(url):
                    self.remote_asset_manager.mark_download_failed(url)
                
                path = MediaDownloader.resolve_source_path(
                    src,
                    storage_dir,
                    on_success_callback=on_success,
                    on_fail_callback=on_fail
                )
                
                if path:
                    # Download bem-sucedido, processa imagem
                    register_slug = cfg.get("register_remote_asset_as")
                    if register_slug and src.startswith("http"):
                        self.remote_asset_manager.register_url(register_slug, src)
                    
                    fit_mode = cfg.get("fit_mode", "cover")
                    
                    if fit_mode == "contain-blur":
                        blur_clip = self._create_blurred_background(path, scene_duration)
                        main_clip = ImageClip(path).set_duration(scene_duration)
                        
                        w, h = main_clip.size
                        target_w, target_h = self.resolution_output
                        
                        scale_w = target_w / w
                        scale_h = target_h / h
                        scale = min(scale_w, scale_h)
                        
                        new_w = int(w * scale)
                        new_h = int(h * scale)
                        
                        main_clip = main_clip.resize(newsize=(new_w, new_h))
                        main_clip = main_clip.set_position("center")
                        
                        final_clip = CompositeVideoClip([blur_clip, main_clip], size=self.resolution_output).set_duration(scene_duration)
                        return final_clip.fl_image(force_rgb)
                    else:
                        clip = ImageClip(path).resize(newsize=self.resolution_output).set_duration(scene_duration)
                        return clip.fl_image(force_rgb)
                
                # Download falhou, URL já foi marcada como inválida pelo callback
                print(f"[BackgroundEngine] ⚠️ Falha no download, tentando próxima URL...")
                # Loop continua automaticamente para tentar próxima URL
        
        # Lógica original para tipos não remote_asset
        if not src:
            raise ValueError("Source da imagem não especificada")
        
        path = MediaDownloader.resolve_source_path(src, storage_dir)
        
        if not path:
            print("[BackgroundEngine] ❌ Falha ao obter imagem, usando cor sólida")
            return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
        
        register_slug = cfg.get("register_remote_asset_as")
        if register_slug and self.remote_asset_manager and src.startswith("http"):
            self.remote_asset_manager.register_url(register_slug, src)
        
        fit_mode = cfg.get("fit_mode", "cover")
        
        if fit_mode == "contain-blur":
            blur_clip = self._create_blurred_background(path, scene_duration)
            main_clip = ImageClip(path).set_duration(scene_duration)
            
            w, h = main_clip.size
            target_w, target_h = self.resolution_output
            
            scale_w = target_w / w
            scale_h = target_h / h
            scale = min(scale_w, scale_h)
            
            new_w = int(w * scale)
            new_h = int(h * scale)
            
            main_clip = main_clip.resize(newsize=(new_w, new_h))
            main_clip = main_clip.set_position("center")
            
            final_clip = CompositeVideoClip([blur_clip, main_clip], size=self.resolution_output).set_duration(scene_duration)
            return final_clip.fl_image(force_rgb)
        else:
            clip = ImageClip(path).resize(newsize=self.resolution_output).set_duration(scene_duration)
            return clip.fl_image(force_rgb)


    def _build_video(self, cfg: Dict, scene_duration: float, storage_dir: str):
        """
        MODIFICADO: Tenta todas as URLs disponíveis antes de usar fallback
        """
        src_type = cfg.get("type", "video")
        src = cfg.get("source")
        
        if src_type == "remote_asset":
            if not self.remote_asset_manager:
                print("[BackgroundEngine] ⚠️ RemoteAssetManager não disponível, usando cor sólida")
                return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
            
            slug = src
            if not slug:
                print("[BackgroundEngine] ❌ Slug não especificado, usando cor sólida")
                return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
            
            # NOVO: Loop tentando todas as URLs disponíveis
            attempt = 0
            while True:
                attempt += 1
                selected_url = self.remote_asset_manager.select_url(slug)
                
                if not selected_url:
                    print(f"[BackgroundEngine] ⚠️ Nenhuma URL válida restante no slug '{slug}', usando cor sólida")
                    return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
                
                src = selected_url
                print(f"[BackgroundEngine] 🎯 Tentativa {attempt}: {src[:50]}...")
                
                def on_success(url):
                    self.remote_asset_manager.mark_download_success(url)
                
                def on_fail(url):
                    self.remote_asset_manager.mark_download_failed(url)
                
                path = MediaDownloader.resolve_source_path(
                    src,
                    storage_dir,
                    on_success_callback=on_success,
                    on_fail_callback=on_fail
                )
                
                if path:
                    register_slug = cfg.get("register_remote_asset_as")
                    if register_slug and src.startswith("http"):
                        self.remote_asset_manager.register_url(register_slug, src)
                    
                    clip = VideoFileClip(path, audio=False).resize(newsize=self.resolution_output)
                    if clip.duration < scene_duration:
                        clip = clip.loop(duration=scene_duration)
                    else:
                        clip = clip.subclip(0, scene_duration)
                    return clip.without_audio()
                
                print(f"[BackgroundEngine] ⚠️ Falha no download, tentando próxima URL...")
        
        # Lógica original para tipos não remote_asset
        if not src:
            raise ValueError("Source do vídeo não especificada")
        
        def on_success(url):
            if self.remote_asset_manager and src_type == "remote_asset":
                self.remote_asset_manager.mark_download_success(url)
        
        def on_fail(url):
            if self.remote_asset_manager and src_type == "remote_asset":
                self.remote_asset_manager.mark_download_failed(url)
        
        path = MediaDownloader.resolve_source_path(
            src,
            storage_dir,
            on_success_callback=on_success,
            on_fail_callback=on_fail
        )
        
        if not path:
            print("[BackgroundEngine] ❌ Falha ao obter vídeo, usando cor sólida")
            return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
        
        register_slug = cfg.get("register_remote_asset_as")
        if register_slug and self.remote_asset_manager and src.startswith("http"):
            self.remote_asset_manager.register_url(register_slug, src)
        
        clip = VideoFileClip(path, audio=False).resize(newsize=self.resolution_output)
        if clip.duration < scene_duration:
            clip = clip.loop(duration=scene_duration)
        else:
            clip = clip.subclip(0, scene_duration)
        return clip.without_audio()

    def _build_ai(self, cfg: Dict, scene_duration: float, storage_dir: str):
        if not AI_AVAILABLE or not self.ai_cache:
            raise ValueError("Sistema de IA não está disponível")

        provider = cfg.get("provider", "pollinations")
        content_type = cfg.get("content_type", "image")
        prompt = cfg.get("prompt", "")
        parameters = cfg.get("parameters", {})
        cache_key = cfg.get("cache_key")

        if not prompt:
            raise ValueError("Prompt não especificado para IA background")

        if not cache_key:
            cache_data = {
                "provider": provider,
                "type": content_type,
                "prompt": prompt,
                "parameters": parameters
            }
            cache_key = hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()[:12]

        cached_file = self.ai_cache.get(cache_key, content_type) if self.ai_cache else None
        if cached_file:
            file_path = cached_file
        else:
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

        if content_type == "image":
            return ImageClip(file_path).resize(newsize=self.resolution_output).set_duration(scene_duration)
        else:
            clip = VideoFileClip(file_path, audio=False).resize(newsize=self.resolution_output)
            if clip.duration < scene_duration:
                clip = clip.loop(duration=scene_duration)
            else:
                clip = clip.subclip(0, scene_duration)
            return clip.without_audio()

    def _select_random_videos_for_duration(self, available_clips: List, target_duration: float) -> List:
        if not available_clips:
            return []

        selected_clips = []
        current_duration = 0.0
        attempts = 0
        max_attempts = len(available_clips) * 3

        available_for_selection = []
        for clip in available_clips:
            clip_path = getattr(clip, 'filename', str(hash(str(clip))))
            if clip_path not in self.last_used_videos:
                available_for_selection.append(clip)

        if not available_for_selection:
            available_for_selection = available_clips.copy()
            self.last_used_videos = []

        import random
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

        if len(self.last_used_videos) > self.max_history:
            self.last_used_videos = self.last_used_videos[-self.max_history:]

        return selected_clips

    def _build_directory(self, cfg: Dict, scene_duration: float) -> Optional:
        source_dir = cfg.get("source")
        if not source_dir:
            raise ValueError("Diretório source não especificado")

        loader = DirectoryType(self.resolution_output, self.dir_clips_cache)
        if source_dir not in self.dir_clips_cache:
            clips = loader.load_clips(cfg, scene_duration)
        else:
            clips = self.dir_clips_cache[source_dir]

        if not clips:
            return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)

        selected = self._select_random_videos_for_duration(clips, float(scene_duration))
        if not selected:
            return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)

        if len(selected) == 1:
            bg_clip = selected[0]
            if bg_clip.duration < scene_duration:
                bg_clip = bg_clip.loop(duration=scene_duration)
            elif bg_clip.duration > scene_duration:
                bg_clip = bg_clip.subclip(0, scene_duration)
            return bg_clip

        bg_clip = concatenate_videoclips(selected, method="compose")
        if bg_clip.duration > scene_duration:
            bg_clip = bg_clip.subclip(0, scene_duration)
        elif bg_clip.duration < scene_duration:
            remaining = scene_duration - bg_clip.duration
            last_clip = selected[-1]
            extra_clip = last_clip.subclip(0, remaining) if last_clip.duration >= remaining else last_clip.loop(duration=remaining)
            bg_clip = concatenate_videoclips([bg_clip, extra_clip], method="compose")
        return bg_clip

    def _apply_animation(self, clip, animation_config: Dict):
        anim_type = animation_config.get("type", "none")
        
        if anim_type == "zoom":
            duration = animation_config.get("duration", 20.0)
            intensity = animation_config.get("intensity", 0.1)
            
            def zoom_effect(get_frame, t):
                frame = get_frame(t)
                
                # CORREÇÃO: Força RGB (3 canais)
                frame = force_rgb(frame)
                
                progress = (t % duration) / duration
                scale = 1.0 + (intensity * np.sin(progress * 2 * np.pi))
                
                h, w = frame.shape[:2]
                new_h, new_w = int(h * scale), int(w * scale)
                
                if scale > 1.0:
                    from PIL import Image
                    pil_img = Image.fromarray(frame.astype('uint8'))
                    pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)
                    resized = np.array(pil_img)
                    
                    y_start = (new_h - h) // 2
                    x_start = (new_w - w) // 2
                    cropped = resized[y_start:y_start+h, x_start:x_start+w]
                    return cropped
                else:
                    return frame
            
            return clip.fl(zoom_effect)
        
        elif anim_type == "fade":
            duration = animation_config.get("duration", 20.0)
            min_opacity = animation_config.get("min_opacity", 0.7)
            
            def fade_effect(get_frame, t):
                frame = get_frame(t)
                
                # CORREÇÃO: Força RGB (3 canais)
                frame = force_rgb(frame)
                
                progress = (t % duration) / duration
                opacity = min_opacity + (1.0 - min_opacity) * (0.5 + 0.5 * np.sin(progress * 2 * np.pi))
                return (frame * opacity).astype('uint8')
            
            return clip.fl(fade_effect)
        
        return clip

    def _apply_filters(self, bg_clip, global_filters_cfg: Dict, scene_filters_cfg: Optional[Dict], scene_duration: float):
        if scene_filters_cfg is not None and isinstance(scene_filters_cfg, dict):
            filters_cfg = Config.deep_merge(global_filters_cfg or {}, scene_filters_cfg)
        else:
            filters_cfg = dict(global_filters_cfg or {})

        if not filters_cfg:
            return bg_clip.fl_image(force_rgb)

        engine = FiltersEngine(self.resolution_output)
        fclip = engine.create_filters_clip(filters_cfg, float(scene_duration))
        if fclip is None:
            return bg_clip.fl_image(force_rgb)
        composed = CompositeVideoClip([bg_clip, fclip], size=self.resolution_output).set_duration(scene_duration)
        return composed.fl_image(force_rgb)

    def build_scene_background(self, global_settings: Dict, scene_data: Dict, scene_duration: float,
                               scene_dir: str, video_dir: str):
        print(f"[BackgroundEngine] Criando fundo para duração: {scene_duration:.2f}s")

        global_background = global_settings.get("background", {}) or {}
        scene_background = scene_data.get("background", None)

        if scene_background is not None:
            background_config = Config.deep_merge(global_background, scene_background)
            storage_dir = scene_dir
            print("[BackgroundEngine] Config de fundo: merge (global + cena)")
        else:
            background_config = dict(global_background)
            storage_dir = video_dir
            print("[BackgroundEngine] Config de fundo: global")

        visual_config = background_config.get("visual", {}) or {}
        bg_type = visual_config.get("type", "color")

        try:
            if bg_type == "color":
                bg_clip = self._build_color(visual_config, scene_duration)
            elif bg_type == "image":
                bg_clip = self._build_image(visual_config, scene_duration, storage_dir)
            elif bg_type == "video":
                bg_clip = self._build_video(visual_config, scene_duration, storage_dir)
            elif bg_type == "ai":
                bg_clip = self._build_ai(visual_config, scene_duration, storage_dir)
            elif bg_type == "directory":
                bg_clip = self._build_directory(visual_config, scene_duration)
            elif bg_type == "remote_asset":
                # Detecta se é imagem ou vídeo pela extensão da URL selecionada
                bg_clip = self._build_image(visual_config, scene_duration, storage_dir)
            else:
                print(f"[BackgroundEngine] ⚠️ Tipo de fundo desconhecido: {bg_type}")
                bg_clip = ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
        except Exception as e:
            print(f"[BackgroundEngine] ❌ Falha ao criar fundo: {e}")
            import traceback
            traceback.print_exc()
            print("[BackgroundEngine] Fallback: preto")
            bg_clip = ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)

        animation_config = visual_config.get("animation", {})
        if animation_config and animation_config.get("type", "none") != "none":
            print(f"[BackgroundEngine] Aplicando animação: {animation_config.get('type')}")
            bg_clip = self._apply_animation(bg_clip, animation_config)

        global_filters = background_config.get("filters", {}) or {}
        scene_filters = scene_background.get("filters") if isinstance(scene_background, dict) else None
        return self._apply_filters(bg_clip, global_filters, scene_filters, scene_duration)
