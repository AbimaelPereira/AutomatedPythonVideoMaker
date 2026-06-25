# `global_settings` e ordem de merge

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

`global_settings` sobrescreve os padrões do canal (`channels_config/{canal}.json`)
e é, por sua vez, sobrescrito por capítulos e cenas. Toda a cadeia usa
`deep_merge` ([utils.py](../../../../libs/utils.py)):

- **Dicts** são mesclados recursivamente (campo a campo).
- **Listas substituem por completo** — não fundem. Isso pega muita gente na
  `palette` do karaokê e no array `scenes`/`chapters` em si.

## Cadeia completa de merge

```
channels_config/{channel_name}.json   (base do canal)
  └─ global_settings                   (do JSON do vídeo)
       └─ global_settings do capítulo   (se usar chapters)
            └─ overrides da cena        (tts, subtitle, transitions, background)
```

Cada nível abaixo vence em caso de conflito. Implementado em
`UnifiedVideoEngine._resolve_scene_gs` e `_normalize_scenes`
([UnifiedVideoEngine.py](../../../../libs/UnifiedVideoEngine.py)).

## Campos aceitos em `global_settings`

| Campo | Ver |
|-------|-----|
| `tts` | [narration_tts.md](narration_tts.md) |
| `subtitle` | [subtitle.md](subtitle.md) |
| `background` | [background.md](background.md) |
| `transitions` | [transitions.md](transitions.md) |
| `padding_top` / `padding_bottom` / `padding_side` | [placement.md](placement.md) |
| `remote_assets` (config do `RemoteAssetManager`, ex.: `selection_mode`) | [background.md](background.md#remote-assets) |

## Capítulos (`chapters`)

Alternativa a `scenes` (lista plana) quando o vídeo tem seções distintas —
ex.: intro/desenvolvimento/conclusão com trilhas sonoras diferentes.

```jsonc
{
  "chapters": [
    {
      "id": "intro",
      "global_settings": {
        "background": { "audio": { "type": "directory", "source": "./assets/audio/background/calm" } }
      },
      "scenes": [ /* cenas da intro */ ]
    },
    {
      "id": "climax",
      "global_settings": {
        "background": { "audio": { "type": "directory", "source": "./assets/audio/background/tense" } }
      },
      "scenes": [ /* cenas do clímax */ ]
    }
  ]
}
```

- `chapter.global_settings` é mesclado por cima do `global_settings` do vídeo
  (não substitui — `deep_merge` recursivo), e vale só para as cenas daquele
  capítulo.
- `chapter.global_settings.background.audio` recebe tratamento especial: é
  mesclado (`deep_merge`) com `global_settings.background.audio` do vídeo,
  permitindo herdar `volume`/`ducking` do global e só trocar a `source`.
- Capítulos são achatados internamente em `_normalize_scenes`: cada cena
  resultante carrega `_chapter_gs` (o `global_settings` do capítulo de origem)
  até ser resolvida em `_resolve_scene_gs`.
- Exemplo completo: [../examples/teste_chapters.json](../examples/teste_chapters.json).

### Armadilha

- **Trilha sonora do capítulo não mudou** → confira se está em
  `chapters[].global_settings.background.audio`, não em
  `chapters[].background.audio` (este último não existe; é sempre dentro de
  `global_settings`).

---

Próximos passos: [channels_config.md](channels_config.md) ·
[scenes.md](scenes.md) · [placement.md](placement.md).
