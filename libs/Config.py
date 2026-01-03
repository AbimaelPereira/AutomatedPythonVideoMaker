import os
import json
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self, video_data=None):
        """
        Inicializa as configurações com a seguinte prioridade (da menor para maior):
        1. Defaults (definidos aqui e no .env)
        2. Configuração do Canal (channels_config/{channel_name}.json)
        3. Configuração do Vídeo (video_data passado pelo main)
        """
        self.video_data = video_data or {}
        
        # Definição de Caminhos Base
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assets_dir = os.path.join(self.base_dir, "assets")
        self.temp_dir = os.getenv("TEMP_DIR", os.path.join(self.base_dir, "temp"))

        # --- 1. DEFINIÇÃO DOS PADRÕES (DEFAULTS) ---
        self.defaults = {
            # Caminhos de arquivos essenciais
            "audio_narration_file": os.getenv("AUDIO_NARRATION_FILE"),
            "subtitle_narration_file": os.getenv("SUBTITLE_NARRATION_FILE"),
            "manchete_file": os.getenv("MANCHETE_FILE"),
            
            # Diretórios de Assets
            "fonts_dir": os.path.join(self.assets_dir, "fonts"),
            "bg_music_dir": os.path.join(self.assets_dir, "audio", "background"),
            "background_videos_dir": os.getenv("BACKGROUND_VIDEOS_DIR", os.path.join(self.assets_dir, "video", "defaults")),
            
            # Configurações de Vídeo e Resolução
            "valid_extensions": ["mp4", "mkv", "avi", "mov", "flv", "webm"],
            "available_resolutions": {"9:16": (1080, 1920), "16:9": (1920, 1080)},
            "output_ratio": os.getenv("OUTPUT_RATIO", "9:16"),
            
            # Layout e Estilo (Valores padrão se nada for informado)
            "padding_bottom": int(os.getenv("PADDING_BOTTOM", 850)), 
            "padding_top": int(os.getenv("PADDING_TOP", 100)),     
            "padding_side": int(os.getenv("PADDING_SIDE", 50)),
            "stack_gap_percent": float(os.getenv("STACK_GAP_PERCENT", 0.02)), 
            
            # Estilo da Legenda (Padrão)
            "font_size": int(os.getenv("FONT_SIZE", 70)),
            "color": "white",
            "stroke_color": "black",
            "stroke_width": int(os.getenv("STROKE_WIDTH", 3)),
            "font": os.path.join(self.assets_dir, "fonts", "Poppins", "Poppins-Bold.ttf"),

            # Youtube e Outros
            "youtube": {
                "token_file_name": "client_secrets.json",
                "privacy_status": "private"
            },
            
            # Necessário para o UnifiedVideoEngine não quebrar se buscar global_settings
            "global_settings": {},

            # Flags de Controle
            "debug_layout": self._to_bool(os.getenv("DEBUG_LAYOUT", False)),
            "debug": self._to_bool(os.getenv("DEBUG", False)),
            "shuffle_clips": self._to_bool(os.getenv("SHUFFLE_CLIPS", True)),
            "max_clips": int(os.getenv("MAX_CLIPS", 0)) or None,
        }

        # --- 2. CARREGAR CONFIGURAÇÃO DO CANAL ---
        channel_config = {}
        channel_name = self.video_data.get("channel_name")
        
        if channel_name:
            channel_file_path = os.path.join(self.base_dir, "channels_config", f"{channel_name}.json")
            if os.path.exists(channel_file_path):
                try:
                    with open(channel_file_path, "r", encoding="utf-8") as f:
                        channel_config = json.load(f)
                    print(f"✅ Configuração do canal '{channel_name}' carregada com sucesso.")
                except Exception as e:
                    print(f"⚠️ Erro ao ler configuração do canal '{channel_name}': {e}")
            else:
                print(f"ℹ️ Arquivo de configuração do canal não encontrado: {channel_file_path}")

        # --- 3. EXECUÇÃO DO DEEP MERGE (FUSÃO) ---
        config_step_1 = self.deep_merge(self.defaults, channel_config)
        self.config = self.deep_merge(config_step_1, self.video_data)

        # --- 4. PÓS-PROCESSAMENTO ---
        if self.config["output_ratio"] in self.config["available_resolutions"]:
            self.config["resolution_output"] = self.config["available_resolutions"][self.config["output_ratio"]]
            self.config["width"], self.config["height"] = self.config["resolution_output"]
        else:
            raise ValueError(f"Resolução não suportada: {self.config['output_ratio']}")

        # Transforma o dicionário final em atributos da classe
        for key, value in self.config.items():
            setattr(self, key, value)

    @staticmethod
    def deep_merge(base, override):
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Config.deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @staticmethod
    def _to_bool(value):
        return str(value).lower() in ("true", "1", "yes", "on")

    def show_configs(self):
        print("\n--- Configuração Final Aplicada ---")
        print(json.dumps(self.config, indent=4, default=str))
        print("-----------------------------------\n")

    def validate(self):
        if not os.path.isdir(self.background_videos_dir):
            os.makedirs(self.background_videos_dir, exist_ok=True)
        if not os.path.isdir(self.temp_dir):
            os.makedirs(self.temp_dir, exist_ok=True)

    # --- MÉTODOS DE COMPATIBILIDADE COM DICIONÁRIO ---
    # Estes métodos permitem que o UnifiedVideoEngine use config.get("chave")
    
    def get(self, key, default=None):
        return self.config.get(key, default)

    def __getitem__(self, key):
        return self.config[key]

    def __contains__(self, key):
        return key in self.config