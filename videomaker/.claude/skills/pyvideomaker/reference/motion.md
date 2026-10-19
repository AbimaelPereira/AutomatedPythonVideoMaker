# `motion` — movimento com keyframes, easing e âncoras

Bloco novo em `visual_elements[]`, irmão de `animation` (legado). Enquanto
`animation` tem 5 tipos fixos, sempre lineares e sempre do início ao fim da
cena, `motion` descreve **o que muda, quando e com que curva** — inclusive
ancorado numa palavra da narração (ver
[sync_narracao.md](sync_narracao.md)).

> Um elemento usa `animation` **ou** `motion`. Declarar os dois aborta o vídeo
> com erro apontando o elemento.

Os dois caminhos de render suportam `motion` por inteiro, então usá-lo **não**
joga a cena no caminho lento (a única exceção é `rotation`, ainda não
implementada em filtro).

## Forma mínima

```jsonc
{
  "type": "image",
  "source": "./assets/image/x.png",
  "placement": { "anchor": ["right", "center"], "width": "45%" },
  "motion": [
    { "at": 0.3, "duration": 0.6, "preset": "slide_in_right" }
  ]
}
```

`"motion": [ … ]` é atalho para `{"actions": [ … ]}`. A forma completa aceita
também `visible` e `on_missing`:

```jsonc
"motion": {
  "on_missing": "proportional",
  "visible": { "from": { "word": "agora" }, "to": { "word": "porém" } },
  "actions": [
    { "name": "entrada", "at": { "word": "dinheiro", "offset": -0.12 },
      "duration": 0.55, "ease": "out_back", "preset": "slide_in_right" },
    { "at": { "after": "entrada", "offset": 0.2 }, "duration": 0.3,
      "ease": "out_quad", "tracks": { "scale": [1.0, 1.08, 1.0] } },
    { "at": { "word": "porém" }, "duration": 0.35, "preset": "fade_out" }
  ]
}
```

## Campos de uma ação

| campo | o que faz |
|---|---|
| `at` | quando começa (âncora — ver abaixo). Ausente = `0` |
| `duration` | duração em segundos. Default: `global_settings.motion.default_duration` (0,5) ou a do preset |
| `until` | âncora de FIM; substitui `duration` |
| `ease` | curva padrão das tracks desta ação |
| `preset` | conjunto pronto de tracks (tabela adiante) |
| `tracks` | o que animar; sobrescreve o preset **propriedade a propriedade** |
| `name` | nome para outra ação referenciar com `{"after": "<name>"}` |
| `hold` | `false` faz o valor voltar à base no fim da ação (default `true`) |
| `loop` | `true` repete o bloco de keyframes até o fim da cena |

## Âncoras (`at`, `until`, `visible.from`, `visible.to`)

| forma | significado |
|---|---|
| `0.8` | segundos absolutos na cena |
| `"42%"` | fração da duração da cena |
| `"start"` / `"end"` | extremos da cena |
| `{"word": "lucro"}` | 1ª ocorrência da palavra na narração |
| `{"word": "lucro", "nth": 2}` | n-ésima ocorrência (1-based) |
| `{"word_index": 14}` | palavra nº 14 (1-based) |
| `{"phrase": "mais de um milhão"}` | sequência de palavras |
| `{"sentence": 2}` | 2ª frase do `narration.text` |
| `{"after": "<name>"}` | fim da ação chamada `<name>` (mesmo elemento) |

Modificadores, combináveis com qualquer forma de objeto:

- `"offset": -0.15` — segundos somados (pode ser negativo)
- `"align": "start" | "end" | "center"` — qual borda da palavra/frase usar
  (default `start`)

## Propriedades animáveis (`tracks`)

| propriedade | unidade | base | observação |
|---|---|---|---|
| `x` | px, `"30%"` (da largura da caixa), `"5vw"` (da tela) | 0 | deslocamento |
| `y` | px, `"30%"` (da altura da caixa), `"5vh"` | 0 | deslocamento |
| `scale` | multiplicador | 1.0 | **transborda** a caixa (pop, punch) |
| `zoom` | multiplicador | 1.0 | **fica dentro** da caixa, recortando (ken burns) |
| `opacity` | 0–1 | 1.0 | |
| `rotation` | graus | 0 | ⚠️ ainda não implementada — joga a cena no MoviePy |

> `scale` e `zoom` não são a mesma coisa e nunca devem ser trocados: `scale`
> faz o elemento crescer **para fora** da caixa (motion de interface); `zoom`
> amplia o conteúdo **dentro** da caixa, que continua do mesmo tamanho no
> layout (efeito ken burns).

## Formas de uma track

```jsonc
"tracks": {
  "opacity": [0, 1],                              // [de, para] na duração da ação
  "scale":   [1.0, 1.08, 1.0],                    // N valores igualmente espaçados
  "y":       [["0%", 40], ["100%", 0]],           // [t_relativo, valor]
  "x":       [[0, "-30%", "out_cubic"], [1, 0]],  // [t_relativo, valor, ease próprio]
  "zoom":    1.1                                  // constante durante a ação
}
```

- `t_relativo`: `0..1` (fração da `duration`), `"40%"` ou `"0.2s"`.
- O `ease` da ação é o default; o 3º item de um keyframe sobrescreve o trecho
  que **começa** nele.
- Antes do 1º keyframe o valor fica segurado no primeiro; depois do último,
  no último (a não ser com `"hold": false`).
- Entre duas ações o valor **fica parado** — não há interpolação fantasma no
  intervalo em que nada foi declarado.

## Easings

`linear`, `in_sine`, `out_sine`, `in_out_sine`, `in_quad`, `out_quad`,
`in_out_quad`, `in_cubic`, `out_cubic`, `in_out_cubic`, `in_quart`,
`out_quart`, `in_out_quart`, `in_expo`, `out_expo`, `in_out_expo`, `in_back`,
`out_back`, `in_out_back`, `out_elastic`, `out_bounce`.

Vocabulário **fechado**: qualquer outro nome aborta o vídeo com sugestão dos
nomes mais próximos.

## Presets

| preset | tracks | duração default |
|---|---|---|
| `fade_in` / `fade_out` | `opacity` | 0,5 s |
| `slide_in_left/right/up/down` | `x` ou `y` (±60% da caixa) + `opacity` | 0,55 s |
| `slide_out_left/right/up/down` | inverso | 0,45 s |
| `pop_in` | `scale` 0,82→1 (`out_back`) + `opacity` | 0,45 s |
| `pop_out` | `scale` 1→0,86 + `opacity` | 0,35 s |
| `punch` | `scale` 1→1,08→1 | 0,3 s |
| `rise` | `y` +40px→0 + `opacity` | 0,5 s |
| `shake` | `x` em senoide amortecida (6 keyframes) | 0,5 s |
| `ken_burns_in` / `ken_burns_out` | `zoom` | a cena inteira |
| `float` | `y` em senoide lenta, com `loop` | 2 s por volta |

`tracks` declarado na ação sobrescreve o do preset só naquela propriedade:

```jsonc
{ "preset": "pop_in", "tracks": { "scale": [0.5, 1.0] } }   // opacity continua vindo do preset
```

## `visible` — janela de exibição

```jsonc
"motion": {
  "visible": { "from": { "word": "agora" }, "to": "80%" },
  "actions": [ { "preset": "fade_in" } ]
}
```

Fora da janela o elemento não é composto. Aceita as mesmas âncoras.

## Stagger (cascata entre elementos)

Na **cena**, não no elemento:

```jsonc
"motion": { "stagger": 0.08, "stagger_group": "cards" }
```

e, em cada elemento do grupo, `"stagger_group": "cards"`. Cada elemento do
grupo recebe `+ i × stagger` em todas as suas ações, na ordem de declaração.

## Defaults globais

```jsonc
"global_settings": {
  "motion": {
    "enabled": true,
    "on_missing": "proportional",
    "default_ease": "out_cubic",
    "default_duration": 0.5
  }
}
```

Mescla na cadeia canal < global < capítulo < cena. `"enabled": false` desliga
todo o motion (os elementos ficam estáticos na posição do layout).

## Quero X → uso Y

| quero | uso |
|---|---|
| elemento entra deslizando da direita | `{"preset": "slide_in_right"}` |
| elemento aparece quando a narração diz "lucro" | `{"at": {"word": "lucro"}, "preset": "pop_in"}` |
| destacar no ritmo da fala | `{"at": {"word": "X"}, "preset": "punch"}` |
| ken burns lento no elemento | `{"preset": "ken_burns_in"}` |
| sumir no fim da cena | `{"at": "80%", "preset": "fade_out"}` |
| só aparecer num trecho | `"visible": {"from": …, "to": …}` |
| cartões entrando em cascata | `motion.stagger` na cena + `stagger_group` nos elementos |
| flutuar o tempo todo | `{"preset": "float"}` |
| movimento combinado | várias ações na lista, encadeadas com `{"after": "<name>"}` |
| voltar ao estado original depois | `"hold": false` |

## Conferir antes de renderizar

```bash
python main.py meu.json --validate        # só o schema (rápido, sem TTS)
python main.py meu.json --timeline-only   # resolve as âncoras e imprime a timeline
MOTION_DEBUG=1 python main.py meu.json    # imprime a timeline durante o render
```

## Armadilhas

- `animation` **e** `motion` no mesmo elemento = erro.
- `opacity` fora de 0–1, `scale`/`zoom` ≤ 0 e `duration` ≤ 0 = erro.
- `{"after": "x"}` só aponta para ação **anterior** e que tenha `name`.
- `x`/`y` em `"%"` são fração da **caixa do elemento**, não da tela — para a
  tela, use `"vw"`/`"vh"`.
- Opacidade com easing não-linear ou entre valores intermediários (0,3 → 0,8)
  usa um caminho de filtro mais caro; prefira `linear` entre 0 e 1 quando o
  tempo de render importar.
- `rotation` ainda não tem equivalente em filtro: a cena cai no MoviePy.
