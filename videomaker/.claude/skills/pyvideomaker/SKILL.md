---
name: pyvideomaker
description: Manual para criar e editar JSONs de vídeo do videomaker (cenas, narração, fundo, transições, legendas e upload). Use ao montar um JSON novo para um canal, ajustar configuração de legenda (subtitle), ou tirar dúvida sobre os campos aceitos pelo pipeline. Acione quando o usuário pedir para "criar um json", "fazer um vídeo", "ajustar a legenda", "configurar karaokê", etc.
---

# Criar JSONs para o videomaker

Manual de criação de JSONs de vídeo para o módulo `videomaker/`. Cada tópico
tem seu próprio arquivo em `reference/`, com campos, defaults reais do código
e armadilhas conhecidas. Exemplos prontos e copiáveis ficam em `examples/`.

## Mapa de referência

| Arquivo | Cobre |
|---------|-------|
| [reference/estrutura-json.md](reference/estrutura-json.md) | Esqueleto do JSON: `slug`, `channel_name`, `output`, `scenes` vs `chapters`, `youtube`, convenção de comentário (`"campo/"`). |
| [reference/global_settings.md](reference/global_settings.md) | Ordem de merge (canal → global → capítulo → cena), `deep_merge`, capítulos (`chapters`). |
| [reference/channels_config.md](reference/channels_config.md) | O que vai em `channels_config/{canal}.json` vs no JSON do vídeo. |
| [reference/scenes.md](reference/scenes.md) | Campos de cena, merge especial de `background` por cena. |
| [reference/narration_tts.md](reference/narration_tts.md) | `narration`, providers TTS (edge/google/polly/kokoro/local_file), `silence_removal`. |
| [reference/background.md](reference/background.md) | `background.visual` (tipos, `fit_mode`, `animation`), `background.audio` (ducking), remote assets. |
| [reference/ai.md](reference/ai.md) | Geração por IA em fundo, `visual_elements` e thumbnail: formato único (`parameters`), default do canal (`global_settings.ai`), fallback de modelo, cache. |
| [reference/visual_elements.md](reference/visual_elements.md) | Tipos de overlay (image/video/directory/text_box/color/gradient/remote_asset), `opacity`, `border_radius`, `animation`, `filters`. |
| [reference/motion.md](reference/motion.md) | `motion`: keyframes, easing, presets, `visible`, stagger — movimento rico em `visual_elements`. **Substitui `animation` (legado).** |
| [reference/sync_narracao.md](reference/sync_narracao.md) | Ancorar o movimento na fala (`{"word": …}`, `{"sentence": …}`), escolha da palavra âncora, `on_missing`, loop de iteração (`--timeline-only`). |
| [reference/placement.md](reference/placement.md) | Bloco `placement` (`anchor`/`width`/`region`) — compartilhado por `visual_elements` e `subtitle`; área segura/paddings. |
| [reference/subtitle.md](reference/subtitle.md) | Legendas: `classic` vs `karaoke`, modos legado/linhas, paletas. **Fonte da verdade para `subtitle`.** |
| [reference/filters.md](reference/filters.md) | `light_leak`, `particles`, `brightness_pulse`, `light_sweep` — `overlay` vs `modifier`. |
| [reference/transitions.md](reference/transitions.md) | Transições `zoom`/`fade`, áudio de transição, override por cena. |
| [reference/output_quality.md](reference/output_quality.md) | `output.ratio`, `output.quality` (presets x264 e override fino), `output.dir` (pasta de saída). |
| [reference/youtube_upload.md](reference/youtube_upload.md) | Upload: `title`/`tags`/`privacy_status`/`publish_at`, thumbnail (file/directory/ai/scene — composta com background + visual_elements). |

## Exemplos prontos (`examples/`)

| Arquivo | Demonstra |
|---------|-----------|
| [examples/teste_karaoke.json](examples/teste_karaoke.json) | Karaokê modo legado e modo linhas. |
| [examples/teste_placement_16x9.json](examples/teste_placement_16x9.json) | `placement` em visual + legenda lado a lado, 16:9. |
| [examples/teste_thumbnail_scene.json](examples/teste_thumbnail_scene.json) | Thumbnail composta (`youtube.thumbnail.type: "scene"`) com fundo de IA + degradê + caixa de texto. |
| [examples/teste_visual_elements.json](examples/teste_visual_elements.json) | image/video/text_box/color, `border_radius`, `animation`, `opacity`, `filters`. |
| [examples/teste_motion.json](examples/teste_motion.json) | `motion`: presets, keyframes explícitos, `{"after": …}`, `visible`, `zoom`. |
| [examples/teste_motion_stagger.json](examples/teste_motion_stagger.json) | `stagger` entre elementos de um grupo + `loop` (`float`). |
| [examples/teste_motion_text_box.json](examples/teste_motion_text_box.json) | `text_box` animado pelo caminho rápido. |
| [examples/teste_motion_narracao.json](examples/teste_motion_narracao.json) | Movimento ancorado em palavras da narração (`{"word": …}`, `{"sentence": …}`). |
| [examples/teste_motion_rotation_blur.json](examples/teste_motion_rotation_blur.json) | `rotation`, `blur` e `motion` no próprio `background.visual`. |
| [examples/teste_transitions.json](examples/teste_transitions.json) | Transição global (`zoom`), override por cena (`fade`), desativação por cena. |
| [examples/teste_chapters.json](examples/teste_chapters.json) | `chapters` com trilha de fundo diferente por capítulo. |
| [examples/teste_canal_completo.json](examples/teste_canal_completo.json) | `output` 2K + `chapters` + `youtube` juntos num só JSON. |

> Templates de cena (composições prontas por estilo visual) vivem **no projeto
> de cada canal**, não nesta skill — a skill documenta os campos do pipeline.

## Velocidade de render: o que o JSON decide

O pipeline tem **dois caminhos** de render por cena, escolhidos automaticamente:

- **rápido** — a cena inteira vira um filtergraph do ffmpeg (~7 s por cena em 1080p);
- **MoviePy** — composição frame a frame em Python (~70 s por cena), usado quando
  algum recurso da cena não tem equivalente fiel em filtro.

Tudo funciona nos dois; a diferença é só tempo. O log diz qual foi usado
(`renderizada (ffmpeg)` vs `Caminho ffmpeg não aplicável (motivo)`).

**Recursos que jogam a cena no caminho lento** (evite se render longo importa):

| Recurso | Alternativa rápida |
|---|---|
| `background` `fit_mode: "contain-blur"` | `contain` (cor sólida) ou `cover` |
| `background` `fit_mode: "contain"` em fundo `video`/`directory` | `cover` |
| `filters` (`light_leak`, `particles`, …) | remover, ou aceitar o custo |
| `transitions` `type: "zoom"` | `type: "fade"` |
| `transitions` com `audio` (sfx) | transição sem áudio |
| `background.visual` `type: "ai"` com `content_type: "video"` | `content_type: "image"` |
| `motion` com `blur` **animado** | `blur` constante (`[6, 6]`), ou aceitar o custo |

Já são rápidos: fundo `color`/`image`/`remote_asset`/`ai`, `cover` com
`focus: "face"`, `fit_mode: "contain"` em fundo de imagem ou IA, modo cover (`placement.width`+`height`), `zoom_in`, `zoom_out`,
`zoom_pulse`, `fade_in`, `fade_zoom_in`, `border_radius`, `opacity`,
`type: "text_box"`, o bloco `motion` inteiro (exceto `rotation`), legendas
`classic` e `karaoke` (inclusive com `shadow.blur`) e transição `fade`.

**Mídia de vídeo também é rápida** (`type: "video"` e `type: "directory"`, tanto
em `background.visual` quanto em `visual_elements`): os trechos viram inputs
normalizados + `concat` no filtergraph. O ganho aqui é menor que o de cenas de
imagem estática (~2x em vez de ~10x), porque os dois caminhos precisam
decodificar os arquivos de origem — o Python deixa de ser o gargalo.

Para comparar os dois caminhos no mesmo JSON:
`RENDER_BACKEND=moviepy|ffmpeg|auto python main.py meu.json`.

## Como usar esta skill

1. Identifique o **canal** (`channel_name`) — a config base dele em
   `channels_config/{canal}.json` já traz `subtitle`, `background`, `tts` etc.
   O JSON do vídeo só precisa do **delta** (o que muda em relação ao canal).
   Ver [reference/channels_config.md](reference/channels_config.md).
2. Lembre da **ordem de merge** (cada um sobrescreve o anterior, via `deep_merge`):
   canal → `global_settings` → `global_settings` do capítulo → cena.
   Dicts são mesclados recursivamente; **listas são substituídas** (atenção à
   `palette` do karaokê e a qualquer outra lista — repita o array inteiro na
   cena se quiser sobrescrever). Ver [reference/global_settings.md](reference/global_settings.md).
3. Para o campo específico que você está editando, abra o arquivo
   correspondente na tabela acima — cada um tem exemplos prontos para copiar.
4. Comentários no JSON: qualquer chave terminada em `/` (ex.: `"tts/"`) é
   ignorada pelo pipeline. Use para manter alternativas desabilitadas no arquivo.

## ⚠️ Antes de rodar um JSON de teste

**O upload para o YouTube não depende de haver bloco `youtube` no JSON do
vídeo** — o `youtube_config` pode vir inteiro do `channels_config/{canal}.json`.
Ou seja: rodar um JSON de teste de um canal configurado **publica um vídeo**.

Para testar sem publicar, use **qualquer um** dos dois:

```bash
DEBUG=1 python main.py meu.json
```
```jsonc
{ "slug": "...", "debug": true }
```

O log confirma com `[UVE] Debug config: True`. Em debug o upload é pulado e os
arquivos intermediários ficam em `output/{slug}/` para inspeção (ou em
`{output.dir}/{slug}/`, se você tiver definido `output.dir`).

## Checklist ao entregar um JSON

- [ ] `slug`, `channel_name`, `output`/`output_ratio` presentes (ou herdados do contexto).
- [ ] **Se for teste: `debug: true` (ou `DEBUG=1`)** — senão pode subir pro YouTube.
- [ ] `subtitle.enabled: true` quando se quer legenda (default é desligado) —
      erro mais comum ao copiar cenas prontas: bloco `subtitle` presente e
      completo, mas sem esse campo → vídeo renderiza sem nenhuma legenda.
- [ ] Fontes referenciadas (`font_path`) existem em `assets/fonts/`.
- [ ] Cores em formato válido (`"#RRGGBB"` ou nome CSS).
- [ ] No karaokê com `palette`: lista completa (não fundirá com a global).
- [ ] `placement` (se usado) coerente com `output_ratio`/`output.ratio` e com os visuais.
- [ ] `visual_elements` não usa `type: "ai"` no próprio elemento (só `image`/
      `video`/`directory`/`text_box`/`color`/`gradient`/`remote_asset`) — IA vai
      dentro de `source`, ver [reference/visual_elements.md](reference/visual_elements.md).
- [ ] Todo bloco de IA tem `model`/`width`/`seed`/… **dentro de `parameters`** —
      chave solta aborta o vídeo. Canal com estilo fixo: `global_settings.ai.parameters`
      com `model` e `enable_fallback: false`. Ver [reference/ai.md](reference/ai.md).
- [ ] Um `visual_element` usa `animation` **ou** `motion`, nunca os dois (aborta).
- [ ] Âncoras de `motion` conferidas com `python main.py meu.json --timeline-only`
      antes de renderizar. Ver [reference/sync_narracao.md](reference/sync_narracao.md).
- [ ] `animation`, `fit_mode` e `fill_color` do fundo ficam **dentro de
      `background.visual`** — em `background` direto são ignorados sem erro.
- [ ] `chapters` (se usado) tem `background.audio` dentro de `global_settings` de cada capítulo, não fora.
