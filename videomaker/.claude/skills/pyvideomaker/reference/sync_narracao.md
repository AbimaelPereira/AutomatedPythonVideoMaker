# Sincronizar movimento com a narração

O pipeline já sabe **quando cada palavra é falada**: o `NarrationEngine` grava
um SRT palavra-a-palavra por cena (`output/{slug}/{cena}/{cena}.srt`), vindo do
provider (edge, polly) ou do Whisper (google, kokoro), já remapeado depois do
corte de silêncio.

Até agora só a legenda usava esses tempos. Com `motion`, qualquer
`visual_elements` pode ancorar seu movimento numa palavra:

```jsonc
{
  "type": "image",
  "source": "./assets/image/grafico.png",
  "placement": { "anchor": ["right", "center"], "width": "40%" },
  "motion": [
    { "at": { "word": "bilhão", "offset": -0.1 }, "preset": "pop_in" }
  ]
}
```

A imagem entra 0,1 s **antes** de a narração dizer "bilhão".

## Como escolher a palavra âncora

O casamento normaliza os dois lados (minúsculas, sem acento, sem pontuação) e,
se não achar igualdade exata, aceita similaridade ≥ 88%.

**Boas âncoras:** palavras **longas e raras** da frase — `"dinheiro"`,
`"bilhão"`, `"aposentadoria"`. Casam sem ambiguidade.

**Âncoras ruins:**

| problema | exemplo | o que fazer |
|---|---|---|
| palavra muito comum | `"de"`, `"o"`, `"que"` | use `nth`, ou ancore numa palavra vizinha com `offset` |
| número escrito em dígito | `"1990"` no texto, "mil novecentos e noventa" na fala | ancore numa palavra vizinha, ou use `{"sentence": n}` |
| sigla ou estrangeirismo | `"IPO"`, `"deadline"` | confira com `--timeline-only` antes |
| palavra que o TTS corta | interjeições, onomatopeias | idem |

Repetição resolve-se com `nth`:

```jsonc
{ "at": { "word": "dinheiro", "nth": 2 } }
```

## Outras formas de ancorar

```jsonc
{ "at": { "phrase": "mais de um milhão" } }   // sequência de palavras
{ "at": { "sentence": 2 } }                   // 2ª frase do narration.text
{ "at": { "word_index": 14 } }                // 14ª palavra da cena
{ "at": { "word": "porém", "align": "end" } } // no FIM da palavra
```

`{"sentence": n}` alinha o texto escrito com o falado por similaridade, então
sobrevive a divergências pontuais (número escrito como dígito, pontuação
diferente). É a âncora mais robusta quando a frase inteira importa mais que a
palavra exata.

## Quando a palavra não casa: `on_missing`

| valor | comportamento |
|---|---|
| `proportional` | **(default)** distribui as ações não resolvidas uniformemente na cena, preservando a ordem |
| `start` | ancora em `t = 0` |
| `skip` | descarta a ação (o elemento fica parado na base) |
| `strict` | aborta o vídeo |

Declarável em `global_settings.motion.on_missing` ou no `motion` do elemento.
Em qualquer política diferente de `strict`, o render **nunca morre** por âncora
não encontrada — ele loga:

```
[Motion] ⚠️ âncora não resolvida: visual_elements[2].motion.actions[1].at:
palavra 'bilhao' não encontrada  próximas: 'bilhoes'(92) 'milhao'(83) …
```

Use `strict` enquanto desenvolve (para o erro aparecer) e deixe
`proportional` em produção (para um TTS diferente não derrubar o vídeo).

## Cena sem narração

Sem `narration`, não há SRT: toda âncora de palavra é um "não encontrado" e cai
no `on_missing`. Prefira âncoras numéricas (`0.8`, `"42%"`) nessas cenas.

## O loop de iteração

Resolver âncoras custa milissegundos; renderizar custa minutos. Antes de
renderizar:

```bash
# 1. o JSON está válido? (sem TTS, instantâneo)
python main.py meu.json --validate

# 2. onde cada ação caiu de fato? (gera só a narração, não renderiza vídeo)
python main.py meu.json --timeline-only

# 3. uma cena só, com detalhe
python -m libs.Motion.inspect meu.json --scene cena_02
```

A saída mostra o instante resolvido e **qual palavra está sendo falada ali**:

```
[Motion] cena_02  dur=7.42s  palavras=23
  elemento[0]  dur=7.42s  tracks=opacity,x
      t=1.84  +0.55  entrada      slide_in_right   ease=out_back  props=opacity,x
            ↳ palavra #6 'dinheiro' (1.84–2.21)
```

Se a seta apontar para a palavra errada, corrija a âncora — sem renderizar.

Durante um render normal, `MOTION_DEBUG=1` imprime essa mesma tabela.

## Receitas

**Elemento acompanha a frase inteira:**
```jsonc
"motion": {
  "visible": { "from": { "sentence": 2 }, "to": { "sentence": 3 } },
  "actions": [ { "at": { "sentence": 2 }, "preset": "fade_in" } ]
}
```

**Destaque no ritmo de três palavras-chave** (um elemento cada):
```jsonc
{ "at": { "word": "primeiro" }, "preset": "punch" }
{ "at": { "word": "segundo" },  "preset": "punch" }
{ "at": { "word": "terceiro" }, "preset": "punch" }
```

**Entra numa palavra e sai em outra:**
```jsonc
"motion": [
  { "name": "in", "at": { "word": "lucro" }, "preset": "slide_in_up" },
  { "at": { "word": "prejuízo", "offset": -0.2 }, "preset": "slide_out_down" }
]
```
