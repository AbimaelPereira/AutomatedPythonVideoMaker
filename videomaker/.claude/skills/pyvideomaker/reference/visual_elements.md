# Elementos visuais (`visual_elements[]`)

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

`visual_elements` é uma lista de overlays posicionados por cima do `background`
da cena, processados por `VisualClip`
([VisualClip.py](../../../../libs/VisualClip.py)) e posicionados pelo
`LayoutEngine` ([LayoutEngine.py](../../../../libs/LayoutEngine.py)).

```jsonc
"visual_elements": [
  {
    "type": "image",
    "source": "./assets/image/foto.png",
    "placement": { "anchor": ["right", "center"], "width": "70%" },
    "filters": { "remove_bg": true },
    "border_radius": 24,
    "animation": { "type": "zoom_in", "start_scale": 1.0, "end_scale": 1.15 }
  }
]
```

## Tipos (`type`)

| `type` | Campos próprios | Observação |
|--------|-------------------|------------|
| `"image"` | `source`, `filters.remove_bg` | `filters.remove_bg: true` remove fundo via `rembg` antes de gerar o clip. |
| `"video"` | `source`, `audio.keep_audio`, `audio.volume` | `audio.keep_audio: false` (default) silencia o vídeo. |
| `"text_box"` | `content`, `style.{font_family,font_size,padding,background_color,text_color,border_radius,strikethrough}` | Renderiza texto como imagem PIL (não usa o `SubtitleEngine`). |
| `"color"` | `color` (hex, default `#000000`) | `ColorClip` sólido — útil como overlay de escurecimento (combine com `placement.width/height` e `opacity`). |
| `"remote_asset"` | `source` (= slug), `register_remote_asset_as` | Resolve slug via `RemoteAssetManager` (mesma mecânica do `background.visual`, ver [background.md](background.md#remote-assets)); despacha para imagem ou vídeo pela extensão do arquivo baixado. |

> **`type: "ai"` não é suportado em `visual_elements`** — só em
> `background.visual`. Tentar usar é silenciosamente ignorado (`clip` fica
> `None` e o elemento não aparece).

## `placement`

Ver [placement.md](placement.md) — campo compartilhado com `subtitle`.
Resumo: `anchor` posiciona dentro da área segura; `width`/`height` controlam
tamanho (width-only = teto com aspect ratio preservado; width+height = modo
cover com crop). Sem `placement.anchor`, o elemento cai no **stack legado**
(empilhado verticalmente, centralizado, com `layout.width`/`layout.position`).

## `opacity`

```jsonc
{ "type": "color", "color": "#000000", "opacity": 0.5, "placement": {...} }
```

Quando `< 1.0`, aplica `set_opacity` no clip antes de posicionar. Útil para
overlays de escurecimento parcial sobre o fundo.

## `filters`

```jsonc
"filters": { "remove_bg": true, "brightness_pulse": { "min": 0.8, "max": 1.1 } }
```

- `remove_bg` é consumido pelo próprio `VisualClip` (não passa pelo
  `FilterEngine`) — só vale para `type: "image"`.
- Os demais nomes (`brightness_pulse`, `light_leak`, `light_sweep`, `particles`)
  vão para o `FilterEngine`: tanto filtros `modifier` (`apply`) quanto `overlay`
  (`compose`) são aplicados ao clip do elemento. Ver [filters.md](filters.md).

## `border_radius`

Cantos arredondados via máscara PIL (`apply_border_radius_clip`). Em
`placement` modo cover (`width`+`height`), é aplicado **depois** do crop, numa
janela de tamanho fixo — para não distorcer com a animação.

## `animation`

```jsonc
"animation": { "type": "zoom_in", "start_scale": 1.0, "end_scale": 1.15, "start_at": 0 }
```

| `type` | Parâmetros |
|--------|------------|
| `"fade_in"` | `duration` (default 1.0) |
| `"zoom_in"` / `"zoom_out"` | `start_scale`, `end_scale` |
| `"zoom_pulse"` | `intensity` (default 0.06) |
| `"fade_zoom_in"` | `start_scale`, `end_scale`, `fade_duration` |

`start_at` atrasa o início da animação (e do clip) em segundos. No modo cover
de `placement` (`width`+`height`), a animação é adiada e roda numa janela
fixa pós-crop — ver [placement.md](placement.md).

## `layout.rotation`

```jsonc
"layout": { "rotation": 15 }
```

Independe de `placement`/stack — aplicado sempre que presente, em graus.

## Armadilhas frequentes

- **Elemento não aparece** → confira `type`; `"ai"` não é suportado aqui (só em
  `background.visual`). Veja logs `[VisualClip]`/`[UVE]` para erros de
  download/geração.
- **`remove_bg` não funciona em vídeo** → só vale para `type: "image"`; vídeos
  não passam por `rembg`.
- **Animação distorce o crop em modo cover** → confira se `placement.width` e
  `placement.height` estão **ambos** presentes; sem os dois, cai no modo
  width-only sem a proteção de janela fixa pós-crop.
- **`opacity` sem efeito** → só é aplicado se `< 1.0` (valor padrão é opaco,
  sem custo extra de processamento quando ausente/1.0).

---

Próximos passos: [placement.md](placement.md) · [filters.md](filters.md) ·
[background.md](background.md).
