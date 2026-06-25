# Posicionamento unificado (`placement`)

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

Tanto `visual_elements[]` quanto `subtitle` aceitam um bloco **`placement`** que
ancora o elemento dentro da **área segura** (margem definida pelos paddings).
`placement` é **opt-in**: ausente → comportamento legado (visual em stack;
legenda via `subtitle_position` + paddings). Zero regressão nos canais já
existentes que não usam `placement`.

```jsonc
"placement": {
  "anchor": ["right", "center"],  // x: left|center|right|"70%"|px • y: top|center|bottom|"50%"|px
  "width":  "70%",                // SÓ visual_elements: largura (fração da área segura ou px)
  "height": "60%",                // SÓ visual_elements, opcional: ver "Modo cover" abaixo
  "region": "30%"                 // SÓ subtitle: confina o texto a uma faixa dessa largura
}
```

## `anchor`

- `anchor[0]` (x): `left` | `center` | `right` | `"70%"` | px — relativo à área segura.
- `anchor[1]` (y): `top` | `center` | `bottom` | `"50%"` | px — relativo à área segura.
- Âncoras nomeadas e percentuais são sempre calculadas **dentro** da área segura
  (nunca encostam fora da margem). Núcleo: `LayoutEngine.resolve_anchor`
  ([LayoutEngine.py](../../../../libs/LayoutEngine.py)).

## `width` (só `visual_elements`)

- `width ≤ 1` ou `"x%"` = fração da largura da área segura; `> 1` = pixels
  (ver `LayoutEngine.calculate_dimension`).
- **Modo width-only** (sem `height`): `width` é um **teto**. A altura é derivada
  pelo aspect ratio original; se estourar a área segura, o elemento é reduzido
  proporcionalmente — a proporção nunca é distorcida. Por isso uma imagem
  vertical em tela 16:9 com `width: "70%"` pode acabar ocupando menos largura
  que o pedido.
- **Modo cover** (`width` **e** `height` juntos): o elemento preenche
  exatamente essa caixa, com crop centralizado no excesso (como `background-size:
  cover` do CSS) — escala pela dimensão que garante cobertura total e recorta o
  sobressalente. Use quando precisa de uma caixa de tamanho fixo (ex.: foto de
  rosto enquadrada). Nesse modo, animação (`animation`) e `border_radius` do
  elemento são adiados e aplicados *depois* do crop, dentro de uma janela de
  tamanho fixo — senão o zoom/crop quebraria o enquadramento.
- **Modo height-only** (`height` sem `width`): `width` é derivado pelo aspect
  ratio, sem clamp adicional na área segura.

## `region` (só `subtitle`)

- Define a largura da faixa de texto; `anchor[0]` define onde a faixa começa.
- `anchor[1]` define o alinhamento vertical do texto dentro da caixa
  (`top`/`center`/`bottom`).
- No **karaokê**, a largura da faixa também encolhe o `font_size` calculado
  dinamicamente (`fit_font_size`): `region: "30%"` → palavras menores.

## Caso de uso clássico — visual + legenda lado a lado

```jsonc
"visual_elements": [
  { "type": "image", "source": "...", "placement": { "anchor": ["right", "center"], "width": "70%" } }
],
"subtitle": {
  "placement": { "anchor": ["left", "center"], "region": "30%" }
}
```

Visual ocupa 70% à direita; legenda fica confinada nos 30% que sobraram à
esquerda, sem sobreposição. Exemplo completo:
[../examples/teste_placement_16x9.json](../examples/teste_placement_16x9.json).

## Paddings = área segura

Margem uniforme onde tudo é ancorado (visual via `placement`, legenda via
`placement` ou modo legado). Defaults dependem da orientação
(`_default_safe_paddings`):

| Orientação | padding_top | padding_bottom | padding_side |
|------------|-------------|-----------------|--------------|
| 9:16 (1080×1920) | 100 | 850 | 50 |
| 16:9 (1920×1080) | ~54 | ~54 | ~96 (≈5% simétrico) |

Sobrescrevíveis em `global_settings` (`padding_top` / `padding_bottom` /
`padding_side`) — ver [global_settings.md](global_settings.md).

Núcleo do cálculo: `LayoutEngine.safe_area` e `LayoutEngine.resolve_anchor`
([LayoutEngine.py](../../../../libs/LayoutEngine.py)),
`SubtitleUtils.resolve_subtitle_box`
([SubtitleUtils.py](../../../../libs/Subtitle/SubtitleUtils.py)).

## Armadilhas frequentes

- **`placement` não tem efeito** → falta `anchor` dentro do bloco; o código só
  trata o item como "placement novo" se `placement.anchor` estiver presente
  (`LayoutEngine.process_stack_layout`). Sem `anchor`, cai no modo legado/stack.
- **Imagem vertical não preenche os 70% pedidos em tela 16:9** → comportamento
  esperado do modo width-only: o teto de largura cede para preservar o aspect
  ratio sem distorcer. Use `width` + `height` (modo cover) se precisar de uma
  caixa de tamanho fixo.
- **Zoom/animação "vaza" da caixa no modo cover** → não deveria: nesse modo a
  animação é adiada para depois do crop e roda dentro de uma janela de tamanho
  fixo. Se acontecer, confira se `width` e `height` estão realmente os dois
  presentes (caso contrário cai no modo width-only, sem essa proteção).
- **`visual_elements` com `type: "ai"`** não é suportado — só `image`, `video`,
  `text_box`, `color`. AI só vale para `background.visual`. Ver
  [visual_elements.md](visual_elements.md).

---

Próximos passos: [visual_elements.md](visual_elements.md) ·
[subtitle.md](subtitle.md) · [global_settings.md](global_settings.md).
