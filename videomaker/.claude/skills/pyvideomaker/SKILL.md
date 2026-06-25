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
| [reference/visual_elements.md](reference/visual_elements.md) | Tipos de overlay (image/video/text_box/color), `opacity`, `border_radius`, `animation`, `filters`. |
| [reference/placement.md](reference/placement.md) | Bloco `placement` (`anchor`/`width`/`region`) — compartilhado por `visual_elements` e `subtitle`; área segura/paddings. |
| [reference/subtitle.md](reference/subtitle.md) | Legendas: `classic` vs `karaoke`, modos legado/linhas, paletas. **Fonte da verdade para `subtitle`.** |
| [reference/filters.md](reference/filters.md) | `light_leak`, `particles`, `brightness_pulse`, `light_sweep` — `overlay` vs `modifier`. |
| [reference/transitions.md](reference/transitions.md) | Transições `zoom`/`fade`, áudio de transição, override por cena. |
| [reference/output_quality.md](reference/output_quality.md) | `output.ratio`, `output.quality` (presets x264 e override fino). |
| [reference/youtube_upload.md](reference/youtube_upload.md) | Upload: `title`/`tags`/`privacy_status`/`publish_at`, thumbnail (file/directory/ai). |

## Exemplos prontos (`examples/`)

| Arquivo | Demonstra |
|---------|-----------|
| [examples/teste_karaoke.json](examples/teste_karaoke.json) | Karaokê modo legado e modo linhas. |
| [examples/teste_placement_16x9.json](examples/teste_placement_16x9.json) | `placement` em visual + legenda lado a lado, 16:9. |
| [examples/teste_visual_elements.json](examples/teste_visual_elements.json) | image/video/text_box/color, `border_radius`, `animation`, `opacity`, `filters`. |
| [examples/teste_transitions.json](examples/teste_transitions.json) | Transição global (`zoom`), override por cena (`fade`), desativação por cena. |
| [examples/teste_chapters.json](examples/teste_chapters.json) | `chapters` com trilha de fundo diferente por capítulo. |
| [examples/teste_canal_completo.json](examples/teste_canal_completo.json) | `output` 2K + `chapters` + `youtube` juntos num só JSON. |

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

## Checklist ao entregar um JSON

- [ ] `slug`, `channel_name`, `output`/`output_ratio` presentes (ou herdados do contexto).
- [ ] `subtitle.enabled: true` quando se quer legenda (default é desligado).
- [ ] Fontes referenciadas (`font_path`) existem em `assets/fonts/`.
- [ ] Cores em formato válido (`"#RRGGBB"` ou nome CSS).
- [ ] No karaokê com `palette`: lista completa (não fundirá com a global).
- [ ] `placement` (se usado) coerente com `output_ratio`/`output.ratio` e com os visuais.
- [ ] `visual_elements` não usa `type: "ai"` (só `image`/`video`/`text_box`/`color`).
- [ ] `chapters` (se usado) tem `background.audio` dentro de `global_settings` de cada capítulo, não fora.
