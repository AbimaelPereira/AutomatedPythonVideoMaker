# channels_config — referência de canal

## Estrutura
```json
{
  "output_ratio": "9:16",
  "global_settings": {
    "tts": { "voice": "pt-BR-AntonioNeural" },
    "subtitle": {
      "font_path": "./assets/fonts/Montserrat/Montserrat-Bold.ttf",
      "font_size": 110,
      "color": "#E5C687",
      "uppercase": true,
      "stroke_enabled": false,
      "shadow_enabled": true,
      "shadow_color": "#A68A56",
      "shadow_opacity": 0.95,
      "blur_radius": 6.0,
      "shadow_offset": [4, 4]
    },
    "background": {
      "visual": {
        "type": "directory",
        "source": "./assets/video/backgrounds",
        "shuffle": true,
        "max_clips": 6,
        "max_clip_duration": 4.0,
        "image_default_duration": 4.0
      },
      "audio": {
        "type": "directory",
        "source": "./assets/audio/canal_music",
        "volume": 0.25
      },
      "filters": {
        "particles": {
          "density": 0.4,
          "speed": 0.7,
          "size": 0.5,
          "movement": "float",
          "blur_radius": 4.0,
          "axis_ratio_range": [0.8, 1.3],
          "color": "#FFD27A"
        }
      }
    }
  },
  "youtube": {
    "token_file_name": "meu_canal.json",
    "privacy_status": "private",
    "category_id": "22"
  }
}
```

## Notas
- `overlays` foi removido; use `background.filters`.
- `directory` usa cache por path (`dir_clips_cache[path] = List[VideoClip]`) e reaproveita clips entre cenas.
- Merge: `scene.background.*` sobrescreve `global_settings.background.*` via `Config.deep_merge`.