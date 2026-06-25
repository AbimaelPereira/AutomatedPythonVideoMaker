# Filtros visuais (`filters`)

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

O bloco `filters` é um dict `nome_do_filtro → params`, despachado pelo
`FilterEngine` ([FilterEngine.py](../../../../libs/Filters/FilterEngine.py)).
Cada filtro declara um `KIND`:

- **`"overlay"`** — gera um clip de luz/partículas composto **por cima** do
  clip base (blend "screen" para luz, alpha para partículas). Usado em
  `background.filters`.
- **`"modifier"`** — modifica o **próprio** clip frame a frame (brilho, clarão
  que varre a tela). Usado em `visual_elements[].filters`.

Vários filtros podem coexistir no mesmo bloco; cada um é aplicado na ordem em
que aparece no dict, só dentro do método do seu `KIND`.

```jsonc
"filters": {
  "light_leak":       { "intensity": 0.8, "count": 2 },          // overlay
  "particles":        { "density": 0.5, "color": "#FFFFFF" },    // overlay
  "brightness_pulse": { "min": 0.75, "max": 1.2, "period": 2.5 },// modifier
  "light_sweep":       { "intensity": 0.8, "period": 4.0 }        // modifier
}
```

## Onde usar cada `KIND`

| Local | `KIND` aceito |
|-------|----------------|
| `background.filters` | `overlay` (via `FilterEngine.compose`) |
| `visual_elements[].filters` | ambos — `modifier` via `apply`, `overlay` via `compose` (em sequência) |

## Filtros disponíveis

### `light_leak` (overlay)

Light leak cinematográfico: a luz entra por UMA borda e decai em gradiente
até o centro, com um "morro" de brilho que desliza ao longo da borda.

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `intensity` | `0.8` | Brilho geral da luz. |
| `size` | `1.0` | Quão fundo a luz penetra a partir da borda. |
| `speed` | `1.0` | Velocidade do deslize/pulsação. |
| `count` | `2` | Quantos vazamentos (cada um numa borda aleatória). |
| `palette` | laranja/âmbar | Lista de cores hex da luz. |

### `particles` (overlay)

Partículas suaves flutuando (poeira/brilhos), com máscara alpha.

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `density` | `0.5` | Quantidade (0–1; ~50 partículas em 1.0). |
| `speed` | `0.5` | Velocidade do movimento. |
| `size` | `0.5` | Tamanho das partículas. |
| `color` | `"#FFFFFF"` | Cor hex. |
| `blur_radius` | `2.0` | Desfoque das partículas. |

### `brightness_pulse` (modifier)

Pulsação suave e contínua de brilho (senoide), tipo luz de estádio.

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `min` | `0.8` | Brilho mínimo do ciclo (1.0 = original). |
| `max` | `1.15` | Brilho máximo do ciclo. |
| `period` | `2.5` | Segundos de um ciclo completo. |

### `light_sweep` (modifier)

Clarão que varre a tela e sai (holofote passando pela lente), diferente do
`brightness_pulse` (que é uniforme) — aqui é uma faixa que se desloca de uma
borda à outra, em loop.

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `intensity` | `0.8` | Brilho do clarão. |
| `width` | `0.3` | Largura da faixa de luz (fração da diagonal). |
| `period` | `4.0` | Segundos de um ciclo completo (entra→atravessa→sai). |
| `angle` | `"random"` | Graus da direção da varredura; `"random"` sorteia por execução. |
| `color` | `"#FFF4E0"` | Cor do clarão (branco levemente quente). |

## Merge entre global e cena

Em `background.filters`, o merge é `deep_merge(global_filters, scene_filters)`
quando a cena define `filters` (campo a campo, já que cada filtro é uma
sub-chave do dict). Se a cena não define `filters`, usa o global inteiro.

## Armadilhas frequentes

- **Filtro "desconhecido" ignorado silenciosamente** → nome errado ou typo;
  confira a lista exata acima (`light_leak`, `particles`, `brightness_pulse`,
  `light_sweep`). O `FilterEngine` loga um aviso e ignora, sem quebrar o vídeo.
- **`brightness_pulse` em `background.filters` não funciona como esperado** →
  é `modifier`, então só tem efeito em `visual_elements[].filters`; em
  `background.filters` apenas filtros `overlay` (`light_leak`, `particles`)
  são aplicados — `compose` filtra por `KIND` e ignora os demais.
- **`light_sweep`/`brightness_pulse` em `background.filters`** — mesmo
  problema ao contrário: são `modifier`, não compõem no fundo via `compose`.
  Se quiser pulsação de brilho no fundo, isso não é suportado diretamente
  hoje — só em `visual_elements`.

---

Próximos passos: [background.md](background.md) · [visual_elements.md](visual_elements.md).
