# Transições entre cenas (`transitions`)

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

`transitions` controla o efeito aplicado entre cenas consecutivas, via
`TransitionEngine` ([TransitionEngine.py](../../../../libs/Transitions/TransitionEngine.py)).
Definido em `global_settings.transitions`; cada cena pode sobrescrever ou
desligar.

## Tipos (`type`)

### `"zoom"` (default)

Zoom out + shake + zoom in — o efeito clássico de "impacto" entre cortes.

```jsonc
"transitions": {
  "enabled": true,
  "type": "zoom",
  "visual": {
    "zoom_max_scale": 15.0,
    "duration": { "zoom_out": 0.2, "shake_out": 0.4, "impulse_in": 0, "zoom_in": 0 },
    "physics":  { "shake_amplitude": 0.12, "shake_frequency": 10, "shake_decay": 10, "impulse_scale": 0.1 }
  },
  "audio": { "type": "directory", "source": "assets/sfx", "volume": 0.8 }
}
```

| Campo | Default | Descrição |
|-------|---------|-----------|
| `zoom_max_scale` | `15.0` | Escala máxima do zoom out/in. |
| `duration.zoom_out` | `0.2` | Segundos do zoom out inicial (ease-out cúbico). |
| `duration.shake_out` | `0.4` | Segundos do "tremor" amortecido após o zoom out. |
| `duration.impulse_in` | `0` | Impulso curto antes do zoom in final (opcional). |
| `duration.zoom_in` | `0` | Segundos do zoom in final (ease-in cúbico). |
| `physics.shake_amplitude` | `0.12` | Amplitude do tremor. |
| `physics.shake_frequency` | `10` | Frequência do tremor. |
| `physics.shake_decay` | `10` | Taxa de decaimento do tremor. |
| `physics.impulse_scale` | `0.1` | Intensidade do impulso (se `impulse_in > 0`). |

### `"fade"`

Fade in no início + fade out no final da cena.

```jsonc
"transitions": {
  "enabled": true,
  "type": "fade",
  "visual": {
    "fade_in_duration": 0.5,
    "fade_out_duration": 0.5,
    "color": [0, 0, 0]
  }
}
```

| Campo | Default | Descrição |
|-------|---------|-----------|
| `fade_in_duration` | `0.5` | Segundos de fade in. |
| `fade_out_duration` | `0.5` | Segundos de fade out. |
| `color` | `[0, 0, 0]` | Cor do fade — aceita `[R,G,B]` ou hex `"#RRGGBB"`. |

## `transitions.audio`

Efeito sonoro tocado na transição (independente da trilha de `background.audio`):

```jsonc
"audio": { "type": "directory", "source": "assets/sfx", "volume": 1.0 }
// ou
"audio": { "type": "file", "source": "assets/sfx/whoosh.mp3", "volume": 1.0 }
```

`type: "directory"` sorteia um `.mp3`/`.wav` da pasta. Vale para ambos os
tipos de transição (`zoom` e `fade`).

## Desativar por cena

```jsonc
{ "id": "cena_03", "transitions": { "enabled": false } }
```

Override simples — desliga a transição global só para essa cena, sem precisar
repetir o resto da config.

## Armadilhas frequentes

- **Transição não aplicada** → confira `transitions.enabled: true` no nível
  efetivo (global ou cena); ausência de `transitions` não liga nada por
  default real (depende do canal/global definir `enabled: true`).
- **Áudio de transição não toca** → `type: "directory"` sem arquivos `.mp3`/
  `.wav` válidos na pasta retorna silenciosamente sem áudio (sem erro).
- **Fade não usa cor esperada** → `color` aceita `[R,G,B]` (0-255 cada) ou hex
  string — confira o formato; valores fora do array de 3 ints caem no default
  preto.

---

Próximos passos: [global_settings.md](global_settings.md) · [scenes.md](scenes.md).
