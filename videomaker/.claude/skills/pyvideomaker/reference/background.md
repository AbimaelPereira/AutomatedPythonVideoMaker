# Fundo de cena (`background`)

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

`background` tem dois blocos independentes: `visual` (o que aparece atrás) e
`audio` (trilha sonora de fundo, separada do TTS de narração). Regras de merge
por cena: ver [scenes.md](scenes.md#merge-de-background-por-cena-comportamento-especial).

```jsonc
"background": {
  "visual": { "type": "directory", "source": "./assets/video/background/x", "fit_mode": "cover" },
  "audio":  { "type": "directory", "source": "./assets/audio/background/x", "volume": 0.2 }
}
```

## `background.visual` — tipos (`type`)

Resolvidos em `BackgroundEngine.build_scene_background`
([BackgroundEngine.py](../../../../libs/Background/BackgroundEngine.py)).

| `type` | Campos | Comportamento |
|--------|--------|----------------|
| `"color"` (default se ausente) | `source` (hex, default `#000000`) | `ColorClip` sólido. |
| `"image"` | `source`, `fit_mode`, `fill_color` | Imagem única. |
| `"video"` | `source`, `fit_mode` | Vídeo único; faz loop ou corta para a duração da cena. |
| `"directory"` | `source`, `shuffle`, `max_clips`, `max_clip_duration`, `image_default_duration` | Sorteia/concatena arquivos de uma pasta (`DirectoryType`) até preencher a duração. |
| `"ai"` | `provider`, `content_type`, `prompt`, `parameters`, `cache_key` | Gera via `AIProviders` (Pollinations), com cache em disco. |
| `"remote_asset"` | `source` (= slug), `register_remote_asset_as` | Resolve um slug via `RemoteAssetManager` — ver seção abaixo. |

### `fit_mode` (para `image`/`video`)

| `fit_mode` | Comportamento |
|------------|----------------|
| `"cover"` (default) | Escala para preencher e corta o excesso, sem distorcer. Aceita `focus: "center"` (default) ou `focus: "face"` (centra o crop no maior rosto detectado, com fallback silencioso pro centro). |
| `"contain"` | Encaixa a imagem inteira, preenchendo as margens com `fill_color` (default preto). |
| `"contain-blur"` | Como `contain`, mas as margens são a própria imagem desfocada (`GaussianBlur` raio 50) em vez de cor sólida. |
| `"cover-zoom"` | Cover com zoom linear unidirecional. Config em `zoom_config`: `direction` (`in`/`out`), `speed`, `start_scale`, `end_scale`. |

### `animation` (dentro de `background.visual`)

```jsonc
"animation": { "type": "zoom", "duration": 20.0, "intensity": 0.12 }
// ou
"animation": { "type": "fade", "duration": 20.0, "min_opacity": 0.7 }
```

- `"zoom"` — pulsação senoidal de escala entre `1±intensity` num ciclo de
  `duration` segundos.
- `"fade"` — pulsação senoidal de opacidade entre `min_opacity` e `1.0`.

### `filters` (dentro de `background`, não de `background.visual`)

```jsonc
"background": {
  "visual": { "type": "directory", "source": "..." },
  "filters": { "light_leak": { "intensity": 0.8 }, "brightness_pulse": { "min": 0.75, "max": 1.2 } }
}
```

Mesclado entre global e cena via `deep_merge` (`_apply_filters`). Ver
[filters.md](filters.md) para os filtros disponíveis.

## `background.audio` — trilha de fundo

```jsonc
"audio": {
  "type": "directory",          // ou "file"
  "source": "./assets/audio/background/suspense",
  "volume": 0.2,                 // default 0.2 — separado do volume da narração
  "ducking": { "enabled": true, "ducking_db": -10.0 }
}
```

- `type: "directory"` sorteia um arquivo (`.mp3`/`.wav`/`.ogg`/`.m4a`) da pasta;
  `type: "file"` (default) usa `source` como caminho direto.
- `ducking.enabled: true` abaixa o volume da trilha durante a fala (detecção de
  voz no áudio da narração), via `AudioEffects.apply_ducking`
  ([AudioEffects.py](../../../../libs/Audio/AudioEffects.py)). Sem ducking, a
  trilha toca no volume fixo o tempo todo.
- Aplicado uma vez por **vídeo inteiro** (ou por capítulo, se usar `chapters`)
  — não por cena. Ver [global_settings.md](global_settings.md#capítulos-chapters).

## Remote assets (`type: "remote_asset"`)

Usado tanto em `background.visual` quanto em `visual_elements[]`. O `source` é
tratado como **slug**, não URL — o `RemoteAssetManager`
([RemoteAssetManager.py](../../../../libs/RemoteAssetManager.py)) escolhe uma
URL válida cadastrada nesse slug (cache em `cache/remote_assets.json`, lido via
`HTTPAssetStorage`/API) e tenta o download, caindo para a próxima URL se
falhar.

```jsonc
"visual": { "type": "remote_asset", "source": "meu_slug", "register_remote_asset_as": "outro_slug" }
```

- `selection_mode` (config global do `RemoteAssetManager`, em
  `global_settings.remote_assets`): `"least_used"` (default — escolhe a URL
  com `lastUsed` mais antigo) ou `"random"`.
- Download bem-sucedido atualiza `lastUsed`; falha marca a URL como `invalid`
  (não será mais selecionada).
- `register_remote_asset_as` — se o `source` resolvido for uma URL HTTP, pode
  ser registrada num novo slug automaticamente (`register_url`), útil para
  reusar mídia baixada de fontes externas em vídeos futuros.
- Se nenhuma URL válida restar no slug, cai em cor sólida preta (fallback
  silencioso, com log).

## Armadilhas frequentes

- **Fundo aparece preto sem erro aparente** → fallback silencioso de
  `BackgroundEngine` para qualquer falha (slug vazio, diretório inexistente,
  download falhou). Confira os logs `[BackgroundEngine]`.
- **`fit_mode: "contain"` com `fill_color` ignorado** → confirme que `fill_color`
  está dentro de `background.visual`, não em `background` direto.
- **`ducking` não reduz o volume da trilha** → exige que o vídeo da cena tenha
  stream de áudio (a narração); sem narração, a música toca em volume cheio e
  o ducking é ignorado silenciosamente.
- **`remote_asset` sempre retorna a mesma mídia** → `selection_mode: "least_used"`
  é o default; se quiser variedade real a cada execução, use `"random"`.

---

Próximos passos: [filters.md](filters.md) · [visual_elements.md](visual_elements.md) ·
[scenes.md](scenes.md).
