import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self):
        def to_bool(value):
            return str(value).lower() in ("true", "1", "yes", "on")

        # Definição de Caminhos Base
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assets_dir = os.path.join(base_dir, "assets")

        defaults = {
            "audio_narration_file": os.getenv("AUDIO_NARRATION_FILE"),
            "subtitle_narration_file": os.getenv("SUBTITLE_NARRATION_FILE"),
            "manchete_file": os.getenv("MANCHETE_FILE"),
            
            # Novos caminhos organizados dentro de /assets
            "fonts_dir": os.path.join(assets_dir, "fonts"),
            "bg_music_dir": os.path.join(assets_dir, "audio", "background"),
            "background_videos_dir": os.getenv("BACKGROUND_VIDEOS_DIR", os.path.join(assets_dir, "video", "defaults")),
            
            "valid_extensions": ["mp4", "mkv", "avi", "mov", "flv", "webm"],
            "available_resolutions": {"9:16": (1080, 1920), "16:9": (1920, 1080)},
            "output_ratio": os.getenv("OUTPUT_RATIO", "9:16"),
            
            # --- CONFIGURAÇÕES DE LAYOUT (TELA 9:16) ---
            "padding_bottom": int(os.getenv("PADDING_BOTTOM", 850)), 
            "padding_top": int(os.getenv("PADDING_TOP", 100)),     
            "padding_side": int(os.getenv("PADDING_SIDE", 50)),    
            "stack_gap_percent": float(os.getenv("STACK_GAP_PERCENT", 0.02)), 
            # -------------------------------------

            "padding": 50, 
            "debug_layout": to_bool(os.getenv("DEBUG_LAYOUT", False)),
            "max_width_percent": 0.6,
            "manchete_opacity": 0.89,
            "crossfade_duration": float(os.getenv("CROSSFADE_DURATION", 0.5)),
            "max_clip_duration": float(os.getenv("MAX_CLIP_DURATION", 8)),
            "max_total_video_duration": None,
            "temp_dir": os.getenv("TEMP_DIR", os.path.join(base_dir, "temp")),
            "max_clips": int(os.getenv("MAX_CLIPS", 0)) or None,
            "shuffle_clips": to_bool(os.getenv("SHUFFLE_CLIPS", True))
        }

        if defaults["output_ratio"] in defaults["available_resolutions"]:
            defaults["resolution_output"] = defaults["available_resolutions"][defaults["output_ratio"]]
            defaults["width"], defaults["height"] = defaults["resolution_output"]
        else:
            raise ValueError(f"Resolução não suportada. Use: {', '.join(defaults['available_resolutions'].keys())}")

        self.config = defaults
        for k, v in defaults.items():
            setattr(self, k, v)

    def show_configs(self):
        for key, value in self.config.items():
            print(f"{key}: {value}")

    def validate(self):
        # Validação ajustada para os novos caminhos
        if not os.path.isdir(self.background_videos_dir):
            os.makedirs(self.background_videos_dir, exist_ok=True)
            print(f"Diretório criado: {self.background_videos_dir}")
            
        if self.manchete_file and not os.path.isfile(self.manchete_file):
            print(f"Aviso: Arquivo de manchete não encontrado: {self.manchete_file}")

    def set_item(self, key, value):
        self.config[key] = value
        setattr(self, key, value)

        if key == "output_ratio":
            if value in self.config["available_resolutions"]:
                self.set_item("resolution_output", self.config["available_resolutions"][value])
                self.set_item("width", self.config["resolution_output"][0])
                self.set_item("height", self.config["resolution_output"][1])
            else:
                raise ValueError(f"Resolução não suportada. Use: {', '.join(self.config['available_resolutions'].keys())}")