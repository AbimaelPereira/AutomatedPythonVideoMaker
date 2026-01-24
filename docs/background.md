# background — visual, áudio e filtros

## Visão geral
- Engine: `libs/Background/BackgroundEngine.py`
- Suporta `background.visual.type`: `color`, `image`, `video`, `ai`, `directory`
- `directory`: usa `libs/Background/DirectoryType.py` para carregar/redimensionar arquivos e cachear por caminho (path -> lista de clips)
- Filtros: `background.filters` (substitui `overlays`); composição sobre o fundo

## Esquema JSON

```json
"global_settings": {
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
}
```

### Tipos suportados (`background.visual.type`)
- `color`
  - `"source": "#000000"` (hex)
- `image`
  - `"source": "./path/to/image.png"`
  - Ajuste: recorte proporcional + resize para resolução alvo
- `video`
  - `"source": "./path/to/video.mp4"`
  - Ajuste: resize; subclip/loop para duração da cena; remove áudio
- `ai`
  - `"provider"`, `"content_type": "image" | "video"`, `"prompt"`, `"parameters"`, `"cache_key"`
  - Geração e cache automático; fallback se indisponível
- `directory`
  - `"source": "./assets/video/backgrounds"`
  - `"shuffle": true | false`
  - `"max_clips": int` (limite de arquivos carregados)
  - `"max_clip_duration": float` (corte por clipe de vídeo)
  - `"image_default_duration": float` (duração por imagem)
  - Comportamento:
    - `DirectoryType.load_clips` retorna lista de clips já redimensionados
    - `BackgroundEngine` seleciona clipes, concatena e ajusta duração final da cena
  - Cache:
    - `dir_clips_cache[path_dir] = List[VideoClip]`
    - Reuso por cenas com diferentes diretórios

## Filtros de fundo (`background.filters`) — substitui `overlays`
- Composição RGBA sobre fundo via `FiltersEngine` (particles implementado)
- Merge: `global_settings.background.filters` pode ser sobrescrito por `scene.background.filters`

Parâmetros `particles`:
- `opacity`: 0..1 (máx por partícula; default 0.8)
- `density`: 0..1 (quantidade; default 0.7)
- `speed`: 0..1 (velocidade; default 0.6)
- `size`: 0..1 (tamanho; default 0.6)
- `movement`: `"scatter" | "float" | "fall"`
- `color`: `#RRGGBB` ou `(r,g,b)`
- `blur_radius`: pixels (default 3.0)
- `axis_ratio_range`: `[min, max]` (ovais; default [0.8, 1.3])
- Avançado:
  - `num_particles`: int
  - `speed_range`: `[min_px_per_s, max_px_per_s]`
  - `size_range`: `[min_px, max_px]`
  - `intensity`: aplica densidade/velocidade/tamanho quando respectivos ausentes

## Exemplos

Global + override por cena:
```json
"global_settings": {
  "background": {
    "visual": { "type": "directory", "source": "./assets/video/bg_default", "shuffle": true, "max_clips": 6 },
    "audio": { "type": "directory", "source": "./assets/audio/bg", "volume": 0.25 },
    "filters": { "particles": { "density": 0.4, "speed": 0.6, "size": 0.5, "color": "#FFFFFF" } }
  }
},
"scenes": [
  {
    "id": "intro",
    "duration": 5.0,
    "background": {
      "visual": { "type": "directory", "source": "./assets/video/intro_bg" },
      "filters": { "particles": { "density": 0.7, "movement": "float", "color": "#FFD27A" } }
    }
  }
]
```

## Migração
- Remover `overlays` do nível da cena/global.
- Adicionar `background.filters` com a mesma estrutura.
- Nenhuma alteração em `visual_elements` (suporta `filters` próprios de elementos).