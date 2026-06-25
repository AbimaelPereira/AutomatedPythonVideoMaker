# Legendas (`subtitle`) — referência completa

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

Tudo sobre legenda vive no objeto **`subtitle`**, definível em três níveis e
mesclado na cadeia **canal < `global_settings` < cena** via `deep_merge`
(dicts fundem recursivamente; **listas substituem** — ver `palette`).
Ver [global_settings.md](global_settings.md) para a cadeia completa de merge.

- Liga/desliga: **`subtitle.enabled`** (default **desligado** quando ausente).
- Não existe mais `narration.subtitles` — foi removido.

O `SubtitleEngine` ([SubtitleEngine.py](../../../../libs/Subtitle/SubtitleEngine.py))
despacha por **`subtitle.type`**:

| `type`      | Comportamento |
|-------------|---------------|
| `"classic"` (default / ausente) | Uma entrada de SRT por vez, estilo único (cor/stroke/sombra). |
| `"karaoke"` | Palavras surgem uma a uma no tempo da fala e se acumulam; limpa em blocos. |

Em ambos os tipos o texto vem de um **SRT gerado palavra-a-palavra** pelo
`NarrationEngine`. Pontuação (`,.?!;:"()[]{}<>-—_`) é removida; `uppercase`
(default `true`) força maiúsculas.

---

## Tipo `classic`

Renderiza cada entrada do SRT como uma imagem (PIL) com stroke e sombra
opcionais, posicionada por `placement` (novo) ou `subtitle_position` + paddings
(legado).

### Campos e defaults (de [ClassicSubtitle.py](../../../../libs/Subtitle/types/ClassicSubtitle.py))

| Campo | Default | Descrição |
|-------|---------|-----------|
| `enabled` | `false` | Liga a legenda. |
| `type` | `"classic"` | — |
| `font_path` | `./assets/fonts/Poppins/Poppins-Black.ttf` | TTF; cai p/ fonte do sistema se faltar. |
| `font_size` | `70` | Tamanho fixo (classic NÃO redimensiona dinamicamente). |
| `color` | `"white"` | Cor do preenchimento. `"#RRGGBB"` ou nome CSS. |
| `uppercase` | `true` | Força maiúsculas. |
| `stroke_enabled` | `true` | Liga o contorno. |
| `stroke_color` | `"black"` | Cor do contorno. |
| `stroke_width` | `3` | **É dobrado internamente** (3 → 6 efetivo). Comportamento legado. |
| `shadow_enabled` | `false` | Liga a sombra. |
| `shadow_color` | `"black"` | Cor da sombra. |
| `shadow_opacity` | `0.8` | 0–1. |
| `blur_radius` | `6.0` | Raio do desfoque gaussiano da sombra. Sombra só aparece com `blur_radius > 0`. |
| `shadow_offset` | `[4, 4]` | Deslocamento `[dx, dy]` da sombra. |
| `subtitle_position` | `"bottom"` | `top` / `center` / `bottom` (legado, usado se não houver `placement`). |
| `placement` | `null` | Posicionamento novo (ver seção Placement). |

### Exemplo `classic`

```json
"subtitle": {
  "enabled": true,
  "type": "classic",
  "font_path": "./assets/fonts/Montserrat/Montserrat-Black.ttf",
  "font_size": 110,
  "color": "#1beb0c",
  "uppercase": true,
  "stroke_enabled": true,
  "stroke_color": "#000000",
  "stroke_width": 2,
  "shadow_enabled": true,
  "shadow_color": "#1beb0c",
  "shadow_opacity": 0.6,
  "blur_radius": 10.0,
  "shadow_offset": [0, 0],
  "subtitle_position": "bottom"
}
```

> Esse é o estilo real do canal `hacker_patriota` (sombra colorida + blur 10 = efeito "glow" verde).

---

## Tipo `karaoke`

As palavras aparecem uma a uma no `start` do SRT e se acumulam. Quando o bloco
fecha, a tela limpa. O **`font_size` é calculado dinamicamente** para preencher a
largura disponível (`fit_font_size`) — **não vem da paleta**. Cada palavra/linha
recebe, em rotação, um item de `palette` (`fill`, `stroke`, `stroke_width`,
`shadow`, `font_path`); a rotação reinicia a cada grupo.

Veja [KaraokeSubtitle.py](../../../../libs/Subtitle/types/KaraokeSubtitle.py).

### Dois modos de agrupamento (escolhidos pela presença dos campos)

| Modo | Ativado quando | Paleta rotaciona | Fonte |
|------|----------------|------------------|-------|
| **LEGADO** (default) | `min_chars_per_line` E `line_fill_ratio` ausentes | por **palavra** | por palavra |
| **LINHAS** (opt-in) | `min_chars_per_line` E/OU `line_fill_ratio` setados | por **linha** | uniforme por linha |

O modo LINHAS resolve o problema de palavra curta órfã/gigante.

### Campos e defaults (de [KaraokeSubtitle.py](../../../../libs/Subtitle/types/KaraokeSubtitle.py))

| Campo | Default | Descrição |
|-------|---------|-----------|
| `enabled` | `false` | Liga a legenda. |
| `type` | — | Deve ser `"karaoke"`. |
| `uppercase` | `true` | Força maiúsculas. |
| `palette` | 1 estilo branco | Lista de estilos (ver abaixo). **Lista → substitui na merge.** |
| `words_per_group` | `4` | (Modo LEGADO) palavras por tela antes de limpar. |
| `layout` | `"one_per_line"` | (Modo LEGADO) `one_per_line` ou `fill_line`. |
| `min_chars_per_line` | `null` | (Ativa modo LINHAS) piso anti-órfã: a linha não fecha antes desse total de caracteres. |
| `line_fill_ratio` | `null` | (Ativa modo LINHAS) teto de largura 0–1: linha fecha se a próxima palavra passar dessa fração da faixa. |
| `lines_per_group` | `3` | (Modo LINHAS) linhas por tela antes de limpar. |
| `max_font_size` | `300` | Teto do fit dinâmico. |
| `min_font_size` | `24` | Piso do fit dinâmico. |
| `line_gap_ratio` | `0.12` | Espaço vertical entre linhas (fração da altura da linha). |
| `subtitle_position` | `"center"` | Legado (se não houver `placement`). |
| `placement` | `null` | Posicionamento novo (ver seção Placement). |

### Estrutura de um item de `palette`

```json
{
  "fill": "#FFFFFF",
  "stroke": "#000000",
  "stroke_width": 3,
  "shadow": { "color": "#000000", "opacity": 0.85, "blur": 6, "offset": [4, 4] },
  "font_path": "./assets/fonts/Montserrat/Montserrat-Black.ttf",
  "uppercase": true
}
```

- `stroke` só aparece se `stroke_width > 0` (o valor também é **dobrado** internamente).
- `shadow` é opcional; se ausente, sem sombra. `offset` = `[dx, dy]`.
- `font_size` **não** existe na paleta — é calculado pelo fit.
- `uppercase` (opcional) — sobrescreve o `uppercase` global **só para este estilo**.
  Ausente = herda o global. Permite, p.ex., deixar apenas uma cor da paleta em
  MAIÚSCULAS e o resto como veio. Vale nos dois modos (por palavra / por linha).

### Exemplo karaokê — modo LEGADO (paleta/fonte por palavra)

```json
"subtitle": {
  "enabled": true,
  "type": "karaoke",
  "words_per_group": 4,
  "layout": "one_per_line",
  "palette": [
    { "fill": "#FFFFFF", "stroke": "#000000", "stroke_width": 3,
      "shadow": { "color": "#000000", "opacity": 0.85, "blur": 6, "offset": [4, 4] },
      "font_path": "./assets/fonts/Montserrat/Montserrat-Black.ttf" },
    { "fill": "#1beb0c",
      "font_path": "./assets/fonts/Montserrat/Montserrat-BlackItalic.ttf" }
  ]
}
```

A 1ª palavra usa o estilo 0, a 2ª o estilo 1, a 3ª volta ao 0… (rotação reinicia a cada grupo de 4).

### Exemplo karaokê — modo LINHAS (paleta/fonte por linha)

```json
"subtitle": {
  "enabled": true,
  "type": "karaoke",
  "min_chars_per_line": 5,
  "line_fill_ratio": 0.85,
  "lines_per_group": 3,
  "palette": [
    { "fill": "#FFFFFF", "stroke": "#000000", "stroke_width": 3,
      "font_path": "./assets/fonts/Montserrat/Montserrat-Black.ttf" }
  ]
}
```

- Linha não fecha antes de 5 caracteres **e** fecha quando a próxima palavra
  passaria de 85% da faixa.
- Última linha órfã (abaixo de `min_chars_per_line`) é grudada na anterior.
- A paleta rotaciona por linha; com 1 item, todas as linhas iguais.

Exemplo completo (ambos os modos): [../examples/teste_karaoke.json](../examples/teste_karaoke.json).

---

## Posicionamento — `placement` (novo) vs legado

`subtitle` aceita o bloco `placement` (`anchor` + `region`) descrito em
[placement.md](placement.md) — é a mesma mecânica usada por `visual_elements[]`,
com `region` no lugar de `width`. No **karaokê**, a largura da faixa também
encolhe o `font_size` (via `fit_font_size`): `region: "30%"` → palavras menores.

Caso de uso clássico: visual 70% à direita + legenda
`anchor: ["left","center"], region: "30%"` = legenda nos 30% à esquerda, sem
sobreposição. Exemplo completo: [../examples/teste_placement_16x9.json](../examples/teste_placement_16x9.json).

### Modo legado (sem `placement`)

Usa `subtitle_position` (`top`/`center`/`bottom`) + paddings
(`padding_top` / `padding_bottom` / `padding_side`) — ver
[placement.md](placement.md) para os defaults de padding por orientação.

Núcleo do cálculo: `SubtitleUtils.resolve_subtitle_box`
([SubtitleUtils.py](../../../../libs/Subtitle/SubtitleUtils.py)).

---

## Armadilhas frequentes

- **Legenda não aparece** → faltou `subtitle.enabled: true` (default é desligado).
- **`palette` da cena não juntou com a global** → correto: listas substituem na
  merge. Repita a paleta inteira na cena se quiser sobrescrever.
- **Sombra não aparece** → `shadow_enabled` ligado mas `blur_radius` em 0; a
  sombra só é desenhada com `blur_radius > 0`.
- **Stroke mais grosso que o esperado** → o `stroke_width` é **dobrado**
  internamente (3 → 6).
- **Fonte caiu para a do sistema** → `font_path` não existe; confira o caminho
  relativo a partir de `videomaker/`.
- **Karaokê com palavra gigante/órfã** → use o modo LINHAS (`min_chars_per_line`
  + `line_fill_ratio`) em vez do legado.

---

Próximos passos: [placement.md](placement.md) (posicionamento) ·
[visual_elements.md](visual_elements.md) (overlays que dividem tela com a legenda) ·
[global_settings.md](global_settings.md) (ordem de merge).
