# Geração por IA (`type: "ai"`)

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

Três lugares do JSON geram imagem por IA (Pollinations), e **todos seguem o
mesmo formato**:

| Onde | Resolvido por |
|---|---|
| `background.visual` | `BackgroundEngine._build_ai` / `SceneBridge.resolve_ai_background` (caminho rápido) |
| `visual_elements[].source` | `UnifiedVideoEngine._resolve_visual_elements_ai_sources` |
| `youtube.thumbnail` (`type: "ai"`) | `YouTube._generate_thumbnail_ai` |

A thumbnail `type: "scene"` usa o `background.visual` normal, então vale a
primeira linha.

## Formato único: argumentos do provider SÓ em `parameters`

```jsonc
{
  "type": "ai",
  "provider": "pollinations",      // default
  "content_type": "image",         // default; "video" só em background.visual
  "prompt": "loose ink pen and watercolor illustration, ...",
  "parameters": { "model": "zimage", "seed": 42 },
  "cache_key": "opcional"           // só background.visual
}
```

Aceitos dentro de `parameters` (repassados ao `PollinationsProvider`):
`model`, `width`, `height`, `seed`, `enhance`, `negative_prompt`, `quality`,
`safe`, `transparent`, `timeout`, `enable_fallback` — e, para vídeo,
`duration`, `aspectRatio`, `audio`, `image`.

> **Chave solta é erro.** `{"type": "ai", "model": "zimage", ...}` aborta o vídeo
> antes do render, com a lista de todos os blocos inválidos
> (`validate_video_ai_blocks`, em
> [params.py](../../../../libs/AIProviders/params.py)). Antes cada caminho lia
> de um lugar diferente e o bloco no formato "errado" perdia o modelo em
> silêncio, caindo no `flux`.

## Precedência

```
defaults do caminho  <  global_settings.ai.parameters  <  bloco.parameters
```

`global_settings.ai.parameters` (no `channels_config` ou no JSON do vídeo) é o
default de **todos** os blocos de IA — é onde um canal com estilo visual fixo
trava o modelo:

```jsonc
// channels_config/meu_canal.json
"global_settings": {
  "ai": { "parameters": { "model": "zimage", "enable_fallback": false } }
}
```

Defaults de cada caminho quando nem o canal nem o bloco definem:

| Caminho | `model` | `width` × `height` | outros |
|---|---|---|---|
| `background.visual` | `flux` | **sempre a resolução de saída** — o que vier é sobrescrito | — |
| `visual_elements[].source` | `flux` | `576` × `1024` | — |
| `youtube.thumbnail` | `flux` | `1280` × `720` | `quality: "hd"`, `negative_prompt` anti-texto |

## Fallback de modelo (`enable_fallback`)

Default `true`: se o modelo pedido falhar, o provider tenta os da lista de
fallback **e devolve sucesso com outro modelo**, só com um aviso no log. Para
canal com estilo fixo isso troca o visual sem erro — use `false`, e a cena falha
em vez de sair diferente.

Listas atuais (aliases conferidos em `gen.pollinations.ai/image/models` em
13/09/2026):

- imagem: `flux` → `zimage` → `klein` → `gptimage`
- vídeo: `veo` → `seedance-2` → `seedance-pro`

Outros aliases de imagem válidos: `kontext`, `seedream`, `nanobanana`,
`gpt-image-2`, `grok-imagine`, `qwen-image`. O catálogo muda — confira em
`https://gen.pollinations.ai/image/models` antes de fixar um modelo novo.

## Cache

- `background.visual` e `visual_elements[].source`: cache **por vídeo** em
  `{output.dir}/{slug}/assets/ai/` (resolvido pelo prepare; ver
  `docs/PREVIEW.md`). A chave é `cache_key` ou o hash de `provider` +
  `content_type` + `prompt` + parâmetros **já resolvidos** (com o default do
  canal) e, no fundo, a resolução de saída. Trocar o modelo do canal gera imagem
  nova. `ai_cache: false` ou `AI_CACHE=0` força regeração. Apagar a pasta do
  vídeo limpa o cache.
- Thumbnail `type: "scene"`: mesmo cache. Thumbnail `type: "ai"` (direto): sem cache.
- Rate limit por provider em `global_settings.ai.rate_limits.<provider>`
  (`max_concurrent`, `rpm`); 429/5xx têm backoff automático.

## `fit_mode` em fundo de IA

Fundo `ai` de imagem faz **resize puro** para a resolução de saída (sem crop),
exceto quando `fit_mode` é `"contain"` ou `"contain-blur"` — aí a imagem inteira
é encaixada, como num fundo `image`. `contain` roda no caminho rápido;
`contain-blur` cai no MoviePy. Ver [background.md](background.md#fit_mode).

## Armadilhas frequentes

- **"Blocos de IA inválidos" ao iniciar** → argumento do provider fora de
  `parameters`. Mova para dentro.
- **Imagem saiu em outro estilo** → o modelo pedido falhou e o fallback trocou.
  Procure `Tentativa 2/` no log `[Pollinations]` e use `enable_fallback: false`.
- **`width`/`height` ignorados no fundo** → esperado: o fundo sempre gera na
  resolução de saída.

---

Próximos passos: [background.md](background.md) ·
[visual_elements.md](visual_elements.md) · [youtube_upload.md](youtube_upload.md).
