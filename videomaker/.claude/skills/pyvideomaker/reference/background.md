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
| `"directory"` | `source`, `fill_strategy`, `no_repeat_window`, `shuffle`, `max_clips`, `max_clip_duration`, `image_default_duration` | Sorteia arquivos de uma pasta até preencher a duração da cena — ver seção abaixo. |
| `"ai"` | `provider`, `content_type`, `prompt`, `parameters`, `cache_key` | Gera via `AIProviders` (Pollinations), com cache em disco. |
| `"remote_asset"` | `source` (= slug), `register_remote_asset_as` | Resolve um slug via `RemoteAssetManager` — ver seção abaixo. |

### `type: "directory"` — como a pasta vira cena

A escolha dos arquivos é feita pelo `DirectorySelector`
([DirectorySelector.py](../../../../libs/Background/DirectorySelector.py)), que
monta um **plano de preenchimento**: a lista de trechos que, emendados, cobrem
exatamente a duração da cena. O mesmo plano vale para os dois caminhos de
render (ffmpeg e MoviePy) e também para `visual_elements` — ver
[visual_elements.md](visual_elements.md).

```jsonc
"visual": {
  "type": "directory",
  "source": "./assets/video/background/suspense",
  "fill_strategy": "prefer_single",   // default
  "no_repeat_window": 20,              // default
  "max_clips": 4,                      // opcional: teto de trechos
  "max_clip_duration": 8,              // opcional: nenhum trecho passa disso
  "image_default_duration": 4          // duração de cada imagem (default 4s)
}
```

**`fill_strategy`** — como preencher a duração:

| valor | Comportamento |
|---|---|
| `"prefer_single"` (**default**) | Usa um arquivo só, se existir algum que cubra a cena inteira; senão concatena. |
| `"concat"` | Sempre emenda vários arquivos até cobrir a duração. |
| `"single"` | Força um arquivo só. Se nenhum cobrir, usa o mais longo em loop. |

> O default é `prefer_single`: cenas cuja pasta tenha clipes longos o bastante
> mostram um vídeo contínuo em vez de vários cortes. Para o comportamento
> antigo (sempre fragmentar), declare `"fill_strategy": "concat"`.

**`no_repeat_window`** (default 20) — quantos sorteios recentes daquela pasta
entram no bloqueio anti-repetição. O histórico é gravado em
`cache/directory_usage.json`, então vale **entre cenas e entre processos** (o
pipeline renderiza cenas em paralelo). Se a janela esvaziar as opções — pasta
menor que a janela —, ela é ignorada: melhor repetir do que ficar sem fundo.
`0` desliga o anti-repetição.

Detalhes que costumam surpreender:

- Quando um arquivo é mais longo que o trecho necessário, o **início é
  sorteado** — a mesma pasta não mostra sempre os primeiros segundos do clipe.
- Se a pasta inteira não bastar para a cena, ela é percorrida de novo
  (reembaralhada) em vez de esticar um clipe em loop.
- Vídeos ilegíveis (sem duração no `ffprobe`) são descartados do sorteio.
- Cobertura vence variedade: se o único arquivo que cobre a cena está bloqueado
  pelo anti-repetição, ele é usado mesmo assim em vez de forçar um loop visível.

### Cache do `type: "ai"`

A imagem gerada é guardada em `cache/ai_generated/` e reaproveitada nas próximas
execuções (a chave vem de `cache_key` ou de um hash de `provider`+`prompt`+
`parameters`). Isso evita chamar a IA de novo a cada render.

Para **forçar regeração**, desligue o cache:

```jsonc
{ "slug": "...", "ai_cache": false }   // na raiz do JSON ou em global_settings
```

```bash
AI_CACHE=0 python main.py meu.json     # aceita 0 / false / off / no
```

Os dois somam — qualquer um dos dois desligando já desliga. Com o cache off, o
log avisa: `[AICache] ⚠️ Cache de IA DESATIVADO`.

> Isso vale para `background.visual` com `type: "ai"`. Imagens de IA em
> `visual_elements` (via `source: {type:"ai"}`) **não usam esse cache** — são
> sempre regeradas, então o switch não muda nada lá.

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

  Campos aceitos dentro de `ducking` (todos opcionais):

  | Campo | Default | O que faz |
  |---|---|---|
  | `ducking_db` | `-18.0` | Quanto abaixar a trilha durante a fala (dB, negativo). |
  | `threshold_db` | `-40.0` | Acima deste nível, a narração conta como "fala". |
  | `attack_ms` | `50` | Tempo para abaixar quando a fala começa. |
  | `release_ms` | `300` | Tempo para voltar ao volume cheio quando a fala para. |
  | `chunk_ms` | `10` | Resolução da análise; raramente precisa mudar. |

  > `-18.0` é bem mais agressivo que o `-10.0` do exemplo acima — se a trilha
  > sumir demais sob a narração, `ducking_db` é o campo a ajustar.
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
