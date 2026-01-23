import DirectoryType
import random
# Imports das suas libs existentes
from libs.MediaDownloader import MediaDownloader 
from libs.AIProviders.AIProviderManager import AIProviderManager
from libs.OverlayEngine import OverlayEngine # <--- Integração solicitada

class BackgroundEngine:
    def __init__(self):
        self.downloader = MediaDownloader()
        self.ai_manager = AIProviderManager() 
        self.overlay_engine = OverlayEngine() # Instancia a engine de overlays existente

        # Transforma o dicionário final em atributos da classe
        for key, value in sel.items():
            setattr(self, key, value)

    def create_background(self, config, duration):
        """
        Gera o background (Visual + Overlays Externos).
        """
        visual_config = config.get("visual", {
            "type": "color",
            "source": "#000000",    
        })

        overlay_config = config.get("overlays", None)

        # 1. Gerar Camada Base (Visual)
        background_clip = self._generate_visual_layer(visual_config, duration)

        # 2. Padronizar (Resize, Crop, Loop/Cut)
        background_clip = self._standardize_clip(background_clip, duration)

        # 3. Aplicar Overlays (Delegando para OverlayEngine)
        if overlay_config:
            print("[BackgroundEngine] Aplicando overlays via OverlayEngine...")
            final_clip = self._apply_overlays_external(background_clip, overlay_config, duration)
            return final_clip
        
        return base_clip

    def _generate_visual_layer(self, config, duration):
        bg_type = config.get("type", "color")
        
        try:
            if bg_type == "directory":
                return self._create_from_directory(self, {
                    "duration": duration,
                    # "preloaded_clips": config.get("parameters", {}).get("preloaded_clips", None),
                })
            elif bg_type == "ai":
                return self._create_from_ai(config)
            elif bg_type == "video":
                return self._create_from_video(config)
            elif bg_type == "image":
                return self._create_from_image(config, duration)
            elif bg_type == "color":
                color = config.get("parameters", {}).get("color", "#000000")
                return ColorClip(size=(self.width, self.height), color=color).set_duration(duration)
            else:
                print(f"[BackgroundEngine] Tipo '{bg_type}' desconhecido. Usando preto.")
                return ColorClip(size=(self.width, self.height), color="#000000").set_duration(duration)
        except Exception as e:
            print(f"[BackgroundEngine] Erro crítico ao gerar visual: {e}. Fallback para preto.")
            return ColorClip(size=(self.width, self.height), color="#000000").set_duration(duration)

    def _create_from_directory(self, params={}):
        defaults = {
            "duration": None,
            "preloaded_clips": None,
            
            "crossfade_duration": 0.8,
            "enable_crossfade": True,

            "max_clip_duration": 4,

            "max_clips": None,
            "shuffle_clips": True,
        }

        params = {**defaults, **params}

        # clips = preloaded_clips if preloaded_clips is not None else self.get_processed_clips()
        clips = params.get("preloaded_clips", None)

        if not clips:
            return None

        if params.get("shuffle_clips", True):
            random.shuffle(clips)

        if params.get("max_clips", None):
            clips = clips[:params["max_files"]]

        # Ajusta a duração de cada clipe
        ajusted_clips = []

        for clip in clips:
            if hasattr(clip, 'duration'):
                if clip.duration > params.get("max_clip_duration", 4):
                    clip = clip.subclip(0, params.get("max_clip_duration", 4))
            else:
                clip = clip.set_duration(params.get("max_clip_duration", 4))
            ajusted_clips.append(clip)

        clips = ajusted_clips

        
        final_duration = 0
        extended_clips = []
        idx = 0
        while True:
            clip = clips[idx % len(clips)]

            if extended_clips:
                nova_duracao = final_duration + clip.duration - params["crossfade_duration"]
            else:
                nova_duracao = final_duration + clip.duration

            if nova_duracao >= duracao:
                restante = duracao - final_duration
                if extended_clips:
                    restante += params["crossfade_duration"]
                if restante < clip.duration:
                    clip = clip.subclip(0, restante)
                extended_clips.append(clip)
                break
            else:
                extended_clips.append(clip)
                final_duration = nova_duracao
                idx += 1
        clips = extended_clips

        if params.get("enable_crossfade", True):

            base = clips[0]
            for next_clip in clips[1:]:
                next_clip = next_clip.crossfadein(params["crossfade_duration"]).set_start(base.duration - params["crossfade_duration"])
                base = CompositeVideoClip([base, next_clip]).set_duration(base.duration + next_clip.duration - params["crossfade_duration"])
            final_video = base
        else:
            final_video = concatenate_videoclips(clips, method='compose')

        if params.get("duration", None):
            final_video = final_video.subclip(0, params["duration"])

        return final_video

    def _create_from_ai(self, config):
        provider = config.get("provider", "pollinations")
        prompt = config.get("prompt")
        params = config.get("parameters", {})
        
        # Injeção de contexto se o prompt vier com placeholders
        # Ex: "Cena de {cenario}" -> "Cena de montanha" (Isso deve ser feito antes, mas aqui garantimos)
        
        image_path = self.ai_manager.generate_image(
            prompt=prompt, 
            provider=provider, 
            width=self.width, 
            height=self.height,
            model=params.get("model", "flux")
        )
        return ImageClip(image_path)

    def _create_from_video(self, config):
        source = config.get("source")
        if source.startswith("http"):
            local_path = self.downloader.download_video(source)
        else:
            local_path = source
        return VideoFileClip(local_path)

    def _create_from_image(self, config, duration):
        source = config.get("source")
        if source and source.startswith("http"):
            local_path = self.downloader.download_image(source)
        else:
            local_path = source
        return ImageClip(local_path)