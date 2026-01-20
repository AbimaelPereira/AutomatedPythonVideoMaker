# channels_config/{channel_name}.json — Configuração por canal (referência e exemplos)

Objetivo: definir valores padrão e sobrescritos por canal. Campos aplicáveis a todo vídeo gerado quando `channel_name` corresponde.

Campos principais (resumido)
- output_ratio: "9:16" | "16:9"
- global_settings: tts, subtitle, background, padding, layout, controls
- youtube: token_file_name, privacy_status, category_id, publish_at, timezone
- metadata: tags, default_title, default_description

Exemplos (válidos para colocar em channels_config/meu_canal.json)

1) Minimal — apenas override de proporção e token
```json
{
  "output_ratio": "9:16",
  "youtube": {
    "token_file_name": "meu_canal_token.json"
  }
}
```

2) Padrões de TTS e legendas
```json
{
  "output_ratio": "16:9",
  "global_settings": {
    "tts": {
      "voice": "pt-BR-FranciscaNeural",
      "rate": "0%",
      "pitch": "0%"
    },
    "subtitle": {
      "font_path": "./assets/fonts/Roboto/Roboto-Bold.ttf",
      "font_size": 72,
      "color": "#FFFFFF",
      "stroke_color": "#000000",
      "stroke_width": 3
    }
  },
  "youtube": {
    "token_file_name": "canal_podcast.json",
    "privacy_status": "unlisted",
    "category_id": "27"
  }
}
```

3) Fundo padrão do canal (vídeos em diretório + áudio)
```json
{
  "global_settings": {
    "background": {
      "visual": {
        "type": "directory",
        "source": "./assets/videos/canal_backgrounds/",
        "loop_background": true
      },
      "audio": {
        "type": "directory",
        "source": "./assets/audio/canal_music/",
        "volume": 0.25
      }
    },
    "shuffle_clips": true,
    "crossfade_duration": 1.0
  },
  "youtube": {
    "token_file_name": "canal_backgrounds.json",
    "privacy_status": "private"
  }
}
```

4) Padrões de layout e espaçamento
```json
{
  "global_settings": {
    "padding_bottom": 700,
    "padding_top": 120,
    "padding_side": 60,
    "stack_gap_percent": 0.02,
    "subtitle": {
      "padding_bottom": 600
    }
  }
}
```

5) Canal multi-config (exemplo com overrides finos)
```json
{
  "output_ratio": "9:16",
  "global_settings": {
    "tts": { "voice": "pt-BR-AntonioNeural" },
    "subtitle": {
      "font_path": "./assets/fonts/Poppins/Poppins-Bold.ttf",
      "font_size": 110
    },
    "background": {
      "visual": { "type": "directory", "source": "./assets/video/vertical/" },
      "audio": { "type": "file", "source": "./assets/audio/canal_theme.mp3", "volume": 0.35 }
    },
    "shuffle_clips": false,
    "max_clips": 6,
    "enable_crossfade": true,
    "crossfade_duration": 0.8
  },
  "youtube": {
    "token_file_name": "canal_vertical.json",
    "privacy_status": "public",
    "category_id": "24"
  }
}
```

Notas práticas
- Campos ausentes são herdados da ordem: defaults do sistema < env < channel_config < vídeo JSON < cena.
- Use channel_config para evitar repetir configurações comuns (fonts, voz, assets).