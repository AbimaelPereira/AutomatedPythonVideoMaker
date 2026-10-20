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
| `"gradient"` | `direction`, `stops[]` | Degradê linear com transparência variável — ver seção abaixo. |
| `"remote_asset"` | `source` (= slug), `register_remote_asset_as` | Resolve slug via `RemoteAssetManager` (mesma mecânica do `background.visual`, ver [background.md](background.md#remote-assets)); despacha para imagem ou vídeo pela extensão do arquivo baixado. |
| `"directory"` | `source`, `fill_strategy`, `no_repeat_window`, `max_clips`, `max_clip_duration`, `image_default_duration`, `audio.keep_audio` | Sorteia arquivos de uma pasta até cobrir a duração da cena — ver seção abaixo. |

> **`type: "ai"` não é suportado em `visual_elements`** — só em
> `background.visual`. Tentar usar é silenciosamente ignorado (`clip` fica
> `None` e o elemento não aparece).
>
> **Mas IA dentro de `source` funciona**: `{"type": "image", "source": {"type":
> "ai", "prompt": "...", "parameters": {"model": "zimage", "width": 1920,
> "height": 1080}}}`. Argumentos do provider **só dentro de `parameters`** —
> `model`/`width`/`height` soltos abortam o vídeo (formato único, ver
> [ai.md](ai.md)). Sem `width`/`height` o default é `576`×`1024`.
> O prepare (`libs/Prepare`) gera a imagem antes do pool de workers, grava em
> `{output.dir}/{slug}/assets/ai/` e troca o `source` pelo caminho do arquivo.
> Mesmo cache do `background.visual`: reaproveitada entre execuções e
> regerada com `ai_cache: false`. Ver `docs/PREVIEW.md`.

## `type: "directory"` — pasta como elemento

Mesma mecânica do fundo (mesmo `DirectorySelector`, mesmos campos, mesmo
histórico anti-repetição em `cache/directory_usage.json`) — ver
[background.md](background.md#type-directory--como-a-pasta-vira-cena) para o
detalhamento de `fill_strategy` e `no_repeat_window`.

```jsonc
{
  "type": "directory",
  "source": "./assets/video/b_roll",
  "fill_strategy": "prefer_single",   // default
  "border_radius": 28,
  "placement": { "anchor": ["right", "center"], "width": "45%" }
}
```

Diferenças em relação ao fundo:

- O **aspect ratio do elemento vem do primeiro arquivo** do plano; os demais são
  ajustados (cover) para o mesmo tamanho antes de emendar. Numa pasta com
  orientações misturadas, o primeiro sorteado decide o formato da caixa.
- Como a pasta é compartilhada com o fundo se apontarem para o mesmo `source`,
  o anti-repetição evita que o mesmo clipe apareça no fundo e no overlay ao
  mesmo tempo.
- `audio.keep_audio` funciona como no `type: "video"` (default silencia).

## `type: "gradient"` — degradê linear

Irmão do `type: "color"`, mas com **opacidade variável ao longo de um eixo**. É o
recurso para escurecer só a faixa onde o texto entra, sem apagar a imagem inteira
(uso típico: thumbnail e legenda sobre fundo claro).

```jsonc
{
  "type": "gradient",
  "direction": "to_top",          // to_top (default) | to_bottom | to_left | to_right
  "stops": [
    { "color": "#000000", "opacity": 0.9, "at": 0.0 },
    { "color": "#000000", "opacity": 0.0, "at": 0.6 }
  ],
  "placement": { "anchor": ["center","center"], "width": "100%",
                 "height": "100%", "relative_to": "screen" }
}
```

- `at` vai de 0 a 1 **na direção declarada**: em `to_top`, `at: 0` é a base.
- Cor e opacidade são interpoladas linearmente entre stops vizinhos; antes do
  primeiro e depois do último, o valor da ponta é mantido.
- Sem `stops`, o default é preto de `opacity` 0 → 1.
- Para cobrir a tela toda use `"relative_to": "screen"` — sem isso, `100%` é
  100% da **área segura** e sobra a moldura do padding.

## `text_box` — contorno, sombra e multilinha

Além de `font_size`/`text_color`/`background_color`, o `style` aceita:

```jsonc
"style": {
  "font_path": "./assets/fonts/Montserrat/Montserrat-Black.ttf",
  "font_size": 96,
  "text_color": "#FFE24A",
  "background_color": "transparent",     // sem caixa; só o texto
  "stroke_color": "#000000", "stroke_width": 8,
  "shadow": { "offset": [6,6], "color": "#000000", "blur": 4, "opacity": 0.8 },
  "line_spacing": 1.05,                  // multiplicador do font_size
  "align": "left"                        // left | center | right (multilinha)
}
```

- `content` aceita `\n` — as linhas são medidas e alinhadas por `align`.
- `line_spacing` é multiplicador (1.0 = padrão da fonte), não pixels.
- `shadow.blur` usa uma camada borrada separada, então não borra o texto nítido.
- `background_color: "transparent"` agora funciona de fato (antes virava um
  retângulo opaco): o clip mantém a máscara alpha.

## `placement`

Ver [placement.md](placement.md) — campo compartilhado com `subtitle`.
Resumo: `anchor` posiciona dentro da área segura; `width`/`height` controlam
tamanho (width-only = teto com aspect ratio preservado; width+height = modo
cover com crop). Sem `placement.anchor`, o elemento cai no **stack legado**
(empilhado verticalmente, centralizado, com `layout.width`/`layout.position`).

## `focus` (modo cover de `placement`)

```jsonc
{ "type": "image", "source": "...", "focus": "face",
  "placement": { "anchor": ["right", "center"], "width": "58%", "height": "85%" } }
```

Chave direta no elemento (mesmo nível de `type`/`source`/`border_radius`), lida
em `UnifiedVideoEngine._cover_crop_offset` — **só tem efeito em modo cover**
(`placement.width` **e** `placement.height` presentes, fazendo `crop_height`/
`crop_width` < tamanho redimensionado). `"face"` centra o crop no maior rosto
detectado (com fallback silencioso pro centro); default `"center"`. Mesma
mecânica de `background.visual` (ver [background.md](background.md#fit_mode-para-imagevideo)),
mas é uma implementação separada — não documentada antes aqui.

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

> **Legado.** Para movimento novo prefira [`motion`](motion.md): keyframes,
> easing, várias ações por elemento, janelas de tempo e âncoras na narração.
> `animation` continua funcionando e não será removida, mas um elemento usa um
> **ou** outro — declarar os dois aborta o vídeo.

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
