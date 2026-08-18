# Saída e qualidade de encoding (`output`)

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

```jsonc
"output": {
  "ratio": "16:9-2k",   // "9:16" | "16:9" | "16:9-2k" (2560x1440) | "9:16-2k" (1440x2560)
  "quality": "high",     // preset OU objeto de override fino
  "dir": "/mnt/videos"   // opcional: onde salvar (default: videomaker/output/)
}
```

Resolvido por `resolve_output_resolution` e `resolve_output_quality`
([utils.py](../../../../libs/utils.py)).

O bloco `output` também pode vir do `channels_config/{canal}.json` — o do vídeo
vence **campo a campo** (`deep_merge`). Útil para fixar `dir` por canal sem
repetir em cada JSON.

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

Controla o encoding x264 do **arquivo final**.

> **Mudou:** antes essa config era aplicada em todos os pontos de render (cena,
> mixagem de áudio e cada concatenação). Hoje as cenas intermediárias são
> encodadas num perfil rápido fixo (`ultrafast`/crf 12, quase sem perda) porque
> são descartadas depois, e a qualidade pedida aqui é aplicada **uma única vez**,
> no encode de saída. A mixagem de áudio e as concatenações intermediárias usam
> `-c:v copy` (sem re-encode). Nada muda no JSON — só ficou mais rápido.
>
> `INTERMEDIATE_ENCODE=0` volta ao comportamento antigo, para comparação.

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

## `output.dir` — salvar em outro lugar

Por padrão a saída vai para `videomaker/output/{slug}/`, e o arquivo final acaba
em `videomaker/output/{slug}.mp4`. `output.dir` troca essa **pasta base**;
o `{slug}` continua sendo acrescentado por baixo dela.

```jsonc
"output": { "dir": "/mnt/hd-externo/renders" }
// → /mnt/hd-externo/renders/{slug}/  durante o render
// → /mnt/hd-externo/renders/{slug}.mp4  no final (fora do debug)
```

- **Absoluto** (`/mnt/videos`) → usado como está.
- **Relativo** (`../renders`) → resolve a partir de `videomaker/` (o `main.py`
  faz `chdir` para lá antes de rodar), **não** da pasta onde você invocou o
  comando.
- **`~`** (`~/videos/renders`) → expandido para o home.
- A pasta é criada se não existir (`makedirs`).
- Ausente → comportamento de sempre (`videomaker/output/`).

Quando `dir` está setado, o log confirma com `[UVE] Diretório de saída: ...`.

Fixar por canal, para todos os vídeos dele:

```jsonc
// channels_config/meu_canal.json
{ "output": { "dir": "/mnt/videos/meu_canal" }, "global_settings": { /* ... */ } }
```

> Só muda **onde** os arquivos são gravados. Cache (`cache/`), tokens
> (`tokens/`) e assets continuam relativos a `videomaker/`.

## Recomendação prática

> Para vídeos longos em 2K, use `"16:9-2k"` + `"high"`. A qualidade é aplicada
> no encode final; não precisa repetir nada no JSON.
>
> Lembre que **2K custa ~44% mais pixels que 1080p em todo o pipeline** —
> inclusive na composição, que é a etapa mais cara. Só suba para `-2k` se
> houver requisito real.

## Armadilhas frequentes

- **`output.quality` com string desconhecida levanta erro** → só os 4 presets
  nomeados são aceitos como string; qualquer outro valor precisa ser objeto.
- **`crf` fora de 0–51** → erro explícito (`ValueError`), não silencioso.
- **`preset` mais lento não deixa o render proporcionalmente mais lento** → em
  conteúdo pouco denso (fundo sólido, zoom lento, karaokê) o x264 é uma fatia
  pequena do tempo; medido em 1080p, o encode puro de uma cena levou ~1,9 s
  contra ~67 s do render inteiro. Trocar `high` por `draft` para "acelerar"
  rende pouco — o custo está na composição, não no encoder.

---

Próximos passos: [estrutura-json.md](estrutura-json.md).
