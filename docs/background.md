# background — configuração visual e áudio (muitos exemplos)

Campos principais
- visual: { type: "image"|"video"|"directory", source, loop_background, max_clip_duration, shuffle }
- audio: { type: "file"|"directory", source, volume, loop }
- crossfade_duration: tempo entre background clips (float)
- enable_crossfade: boolean
- max_clips: limite de clipes selecionados de um diretório
- output_ratio / resolution_output: permite override da resolução final

Exemplos variados

1) Background com imagem única
```json
"background": {
  "visual": {
    "type": "image",
    "source": "./assets/backgrounds/single_bg.jpg"
  }
}
```

2) Background com vídeo único e loop
```json
"background": {
  "visual": {
    "type": "video",
    "source": "./assets/video/bg_loop.mp4",
    "loop_background": true
  }
}
```

3) Background a partir de diretório (embaralhado, crossfade)
```json
"background": {
  "visual": {
    "type": "directory",
    "source": "./assets/video/backgrounds/",
    "shuffle": true,
    "max_clips": 8,
    "max_clip_duration": 4
  },
  "crossfade_duration": 0.9,
  "enable_crossfade": true
}
```

4) Background áudio: único arquivo
```json
"background": {
  "audio": {
    "type": "file",
    "source": "./assets/audio/background_music.mp3",
    "volume": 0.25,
    "loop": true
  }
}
```

5) Background áudio: diretório com seleção aleatória
```json
"background": {
  "audio": {
    "type": "directory",
    "source": "./assets/audio/bgs/",
    "volume": 0.3,
    "loop": true
  }
}
```

6) Completo — vídeo directory + música directory + overrides
```json
"background": {
  "visual": {
    "type": "directory",
    "source": "./assets/video/vertical_backgrounds/",
    "shuffle": false,
    "max_clips": 5,
    "max_clip_duration": 6
  },
  "audio": {
    "type": "directory",
    "source": "./assets/audio/soft_loop/",
    "volume": 0.18
  },
  "enable_crossfade": true,
  "crossfade_duration": 1.2
}
```

7) Forçar resolução de saída para backgrounds (quando precisa de crop/resize)
```json
"background": {
  "visual": {
    "type": "directory",
    "source": "./assets/video/backgrounds/",
    "shuffle": true
  },
  "resolution_output": [1080, 1920]
}
```

8) Caso de fallback: imagem + áudio local se diretório vazio
```json
"background": {
  "visual": {
    "type": "directory",
    "source": "./assets/video/maybe_empty/",
    "shuffle": true
  },
  "fallback": {
    "visual": { "type": "image", "source": "./assets/images/default_bg.jpg" },
    "audio": { "type": "file", "source": "./assets/audio/default_bg.mp3", "volume": 0.2 }
  }
}
```

Exemplo de vídeo completo (contexto de uso em vídeo JSON)
```json
[
  {
    "slug": "video_com_background_exemplo",
    "output_ratio": "9:16",
    "global_settings": {
      "background": {
        "visual": {
          "type": "directory",
          "source": "./assets/video/vertical_bg/",
          "shuffle": true,
          "max_clips": 6
        },
        "audio": {
          "type": "file",
          "source": "./assets/audio/theme_loop.mp3",
          "volume": 0.28
        }
      },
      "crossfade_duration": 0.8
    },
    "scenes": [
      {
        "id": "cena1",
        "duration": 5,
        "narration": { "text": "Abertura", "subtitles": true }
      }
    ]
  }
]
```

Regras operacionais
- Quando visual.type == "directory": engine filtra por extensões válidas (mp4,mkv,avi,mov,flv,webm).
- Se crossfade habilitado e vídeos curtos, ajuste max_clip_duration para evitar cortes bruscos.
- volume aceitável: 0.0 a 1.0; valores < 0.3 recomendados para música de fundo.
- fallback útil em pipelines automatizados para evitar erro quando diretório estiver vazio.

Fim.