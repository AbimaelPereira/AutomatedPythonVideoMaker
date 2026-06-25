# Cenas (`scenes[]`)

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

Cada cena é processada de forma independente (sequencial ou em paralelo via
`ProcessPoolExecutor`, controlado por `MAX_PARALLEL_SCENES`). Depois, os MP4s
de cada cena são concatenados via FFmpeg e o áudio de fundo é misturado.

## Campos de uma cena

```jsonc
{
  "id": "cena_01",
  "narration": { "text": "..." },         // ver narration_tts.md
  "duration": 5.0,                         // opcional; default = duração do TTS
  "background": { "visual": {...}, "audio": {...} }, // ver background.md
  "visual_elements": [ /* ... */ ],        // ver visual_elements.md
  "transitions": { "enabled": false },     // override por cena — ver transitions.md
  "tts": { "provider": "edge" },           // override de provider por cena
  "subtitle": { "enabled": true, "font_size": 90 } // override de legenda por cena
}
```

| Campo | Obrigatório | Descrição |
|-------|--------------|-----------|
| `id` | sim | Identificador da cena; usado em nomes de arquivo temporário e logs. |
| `narration.text` | não | Texto a sintetizar. Cena sem narração usa duração fixa (default 4.0s, ver `duration`). |
| `duration` | não | Duração fixa da cena. Se ausente, usa a duração do áudio TTS gerado. |
| `background` | não | Se ausente, herda o `background` global por completo. Se presente, é mesclado (`deep_merge`) com o global. Ver [background.md](background.md). |
| `visual_elements` | não | Lista de overlays (imagem/vídeo/texto/cor) posicionados pelo `LayoutEngine`. Ver [visual_elements.md](visual_elements.md). |
| `transitions` | não | Override por cena (ex.: `{"enabled": false}` desliga a transição global só nessa cena). Ver [transitions.md](transitions.md). |
| `tts` | não | Override de `provider`/`voice`/`rate`/`pitch`/etc. por cena. Ver [narration_tts.md](narration_tts.md). |
| `subtitle` | não | Override de estilo de legenda por cena. Ver [subtitle.md](subtitle.md). |

## Merge de `background` por cena: comportamento especial

Diferente dos outros campos, `background` da cena **não é sempre mesclado**
com o global — depende de estar presente ou não:

- **Cena sem `background`** → usa o `global_settings.background` inteiro, e os
  assets temporários são salvos no diretório do vídeo (compartilhado entre
  cenas, útil para `directory`/`remote_asset` reusarem cache).
- **Cena com `background`** → faz `deep_merge(global_background, scene_background)`
  e salva os assets temporários no diretório da própria cena.

Implementado em `BackgroundEngine.build_scene_background`
([BackgroundEngine.py](../../../../libs/Background/BackgroundEngine.py)).

## Armadilhas frequentes

- **Cena sem narração dura só 4 segundos** → é o default; defina `duration`
  explicitamente para cenas sem `narration.text`.
- **Mudar 1 campo de `background` na cena reseta o resto** → não deveria: é
  `deep_merge`, então só o campo informado sobrescreve. Se o resultado não é o
  esperado, confira se o campo é uma lista (substitui) em vez de dict.

---

Próximos passos: [narration_tts.md](narration_tts.md) ·
[background.md](background.md) · [visual_elements.md](visual_elements.md).
