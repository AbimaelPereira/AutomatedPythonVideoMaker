# Saída e qualidade de encoding (`output`)

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

```jsonc
"output": {
  "ratio": "16:9-2k",   // "9:16" | "16:9" | "16:9-2k" (2560x1440) | "9:16-2k" (1440x2560)
  "quality": "high"      // preset OU objeto de override fino
}
```

Resolvido por `resolve_output_resolution` e `resolve_output_quality`
([utils.py](../../../../libs/utils.py)).

## `output.ratio`

| Valor | Resolução |
|-------|-----------|
| `"9:16"` (default) | 1080×1920 |
| `"16:9"` | 1920×1080 |
| `"16:9-2k"` | 2560×1440 |
| `"9:16-2k"` | 1440×2560 |

**Retrocompat**: `output_ratio` solto na raiz do JSON ainda é aceito e
equivale a `output.ratio`.

## `output.quality`

Controla o encoding x264, aplicado em **todos** os pontos de render: cenas
(paralelo/sequencial), mixagem de áudio e re-encodes de concatenação.

### Presets nomeados (string)

| Preset | crf | preset x264 | fps |
|--------|-----|-------------|-----|
| `"draft"` | 26 | `veryfast` | 30 |
| `"balanced"` | 20 | `medium` | 30 |
| `"high"` (default quando ausente) | 18 | `slow` | 30 |
| `"max"` | 16 | `slower` | 30 |

### Objeto de override fino

```jsonc
"output": { "quality": { "preset": "high", "crf": 16, "fps": 30, "pix_fmt": "yuv420p" } }
```

- `preset` (dentro do objeto) parte de um preset nomeado (base) **ou** aceita
  um preset x264 cru (`ultrafast`...`placebo`) diretamente.
  Qualquer outra chave do objeto sobrescreve o valor do preset base.
- `crf`: 0–51, menor = mais qualidade e arquivo maior. Validado (erro se fora
  do intervalo).
- `preset` x264 final é validado contra a lista oficial
  (`ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow, placebo`).

## Recomendação prática

> Para vídeos longos em 2K, use `"16:9-2k"` + `"high"`. A qualidade é definida
> já na render de cena; a concatenação re-encoda por cima usando a mesma
> config — é o que o pipeline faz automaticamente, sem precisar repetir nada.

## Armadilhas frequentes

- **`output.quality` com string desconhecida levanta erro** → só os 4 presets
  nomeados são aceitos como string; qualquer outro valor precisa ser objeto.
- **`crf` fora de 0–51** → erro explícito (`ValueError`), não silencioso.
- **Qualidade "não aplicada" na concatenação final** → não deveria acontecer;
  o pipeline usa a mesma config de qualidade em cena e concatenação
  automaticamente. Se notar diferença visual, confira se há reprocessamento
  fora do pipeline padrão.

---

Próximos passos: [estrutura-json.md](estrutura-json.md).
