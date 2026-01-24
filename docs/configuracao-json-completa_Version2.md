# Configuração JSON Completa — Versão 2 (atualizada)

## Básico
```json
[
  {
    "slug": "video_exemplo",
    "channel_name": "meu_canal",
    "output_ratio": "9:16",
    "global_settings": {
      "tts": { "voice": "pt-BR-AntonioNeural" },
      "subtitle": {
        "font_path": "./assets/fonts/Montserrat/Montserrat-Bold.ttf",
        "font_size": 85,
        "color": "#F0F0F0",
        "stroke_color": "#1A1A1A",
        "stroke_width": 2
      },
      "background": {
        "visual": {
          "type": "directory",
          "source": "./assets/video/vertical_bg",
          "shuffle": true,
          "max_clips": 6,
          "max_clip_duration": 4.0,
          "image_default_duration": 4.0
        },
        "audio": {
          "type": "file",
          "source": "./assets/audio/theme_loop.mp3",
          "volume": 0.28
        },
        "filters": {
          "particles": {
            "density": 0.4,
            "speed": 0.6,
            "size": 0.5,
            "movement": "float",
            "blur_radius": 4.0,
            "axis_ratio_range": [0.8, 1.3],
            "color": "#FFFFFF"
          }
        }
      }
    },
    "scenes": [
      {
        "id": "cena_001",
        "narration": { "text": "Texto a ser narrado", "subtitles": true },
        "duration": 5.0
      }
    ]
  }
]
```

## Fundo (`background`)
### Visual
- `type`: `color` | `image` | `video` | `ai` | `directory`
- `directory`:
  - `source`: pasta com vídeos/imagens
  - `shuffle`, `max_clips`, `max_clip_duration`, `image_default_duration`

### Áudio
- `type`: `file` | `directory`
- `source`: caminho
- `volume`: 0..1

### Filtros (substitui `overlays`)
- `background.filters.particles`: ver documentação em `docs/background.md`

Exemplo override por cena:
```json
"scenes": [
  {
    "id": "intro",
    "narration": { "text": "Bem-vindo!", "subtitles": true },
    "background": {
      "visual": { "type": "directory", "source": "./assets/video/intro_bg" },
      "filters": { "particles": { "density": 0.7, "movement": "float", "color": "#FFD27A" } }
    },
    "visual_elements": []
  }
]
```

## Elementos Visuais (`visual_elements`)
- Tipos: `"image" | "video" | "text_box"`
- `filters` em elementos continuam (ex.: `remove_bg`, `blur`, `brightness`, `contrast`)

Exemplo imagem:
```json
{
  "type": "image",
  "source": "./assets/images/logo.png",
  "layout": { "width": "50%", "position": "center", "margin": 20, "rotation": 0 },
  "animation": { "type": "fade_in", "duration": 1.0, "start_at": 0.5 },
  "filters": { "remove_bg": true }
}
```