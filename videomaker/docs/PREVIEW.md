# Prepare e Preview

Três fluxos, todos começam pelo prepare:

```
prepare            → só resolve assets
prepare → preview  → PNG por cena
prepare → render   → vídeo final (reaproveita os assets já preparados)
```

## Layout de pastas

```
{output.dir}/{slug}/
├── assets/
│   ├── manifest.json       # asset_key → arquivo + metadados (caminhos relativos)
│   ├── ai/                 # imagens/vídeos de IA
│   └── dl/                 # downloads de URL e remote_asset
├── previews/
│   ├── NN-<scene_id>.png   # NN = índice 1-based (3 dígitos se >99 cenas)
│   ├── .cache.json         # hash por cena
│   └── result-<job>.json   # resultado dos jobs da API
├── thumbnail.png
└── <scene_id>/ ... , <slug>.mp4   # render
```

Nada é cacheado fora da pasta do vídeo (o `AICache` global foi removido).
Apagar `{output.dir}/{slug}/` limpa tudo.

## Prepare

Resolve para `assets/` o que as cenas precisam: imagens de IA (fundo e
`visual_elements[].source`), URLs e `remote_asset`. Paralelo, deduplicado por
`asset_key`, uma falha não derruba as outras (vai em `failed`).

- `remote_asset`: a URL escolhida fica **fixada** no manifest. O mesmo vídeo
  usa sempre a mesma mídia, mesmo com `selection_mode: random`/`least_used`.
- `type: "directory"` **não** é fixado: a escolha depende da duração da cena
  (pós-TTS) e continua sendo feita no render.
- Narração/TTS fora do prepare.
- `--force` ignora o cache. `"ai_cache": false` (raiz ou `global_settings`) ou
  `AI_CACHE=0` fazem os assets de **IA** serem regerados; downloads continuam
  vindo do cache.

### Rate limit

Por provider: concorrência, RPM e backoff exponencial em 429/5xx (2, 4, 8, 16 s;
respeita `Retry-After`). Defaults: `pollinations` 2 simultâneas / 20 rpm,
`modelscope` 1 / 10, downloads 8 / sem limite.

```jsonc
"global_settings": { "ai": { "rate_limits": { "pollinations": { "max_concurrent": 1, "rpm": 6 } } } }
```

## Preview

Um PNG por cena, em **pose de repouso**: cada elemento no `placement` final,
sem `animation` nem `motion`; fundo sem zoom/pan. Serve para ajustar layout.

O que o preview **não** valida: fade, slide, zoom em movimento, transições,
legenda e sincronia com a narração.

Cache por hash de cena (`background`, `visual_elements`, resolução, paddings,
`ai.parameters`, fingerprint dos assets). Mudar só `narration`, `subtitle`,
`transitions`, `duration` ou `tts` não re-renderiza. `--force` ignora.
Execução do vídeo inteiro remove PNGs de cenas que não existem mais.

## CLI

```bash
python3 main.py video.json --prepare                 # só assets
python3 main.py video.json --preview                 # prepare + PNGs
python3 main.py video.json --preview --scenes cena_02,5 --force
```

`--scenes` aceita ids ou índices 1-based. A última linha do stdout é o JSON do
resultado (array se o arquivo for uma lista). Código de saída 1 para JSON
inválido, slug ausente ou cena inexistente; falhas de asset individuais não
mudam o código.

## Thumbnail

`youtube.thumbnail` com `type: "scene"` usa o mesmo motor (`libs/Thumbnail/Thumbnail.py`,
`build_thumbnail`). Aceita 16:9 (≥640 de largura) e 9:16 (≥640 de altura);
sem `width`/`height` usa 1280x720 ou 720x1280 pela orientação do vídeo.
Itens inválidos (`animation`, `motion`, `narration`, `subtitle`, chaves
desconhecidas, proporção fora do padrão) viram aviso e são ignorados. Saída:
`{output.dir}/{slug}/thumbnail.png`, recomprimida em JPEG só se passar de 2 MB.
`ThumbnailRenderer` foi removido.

## API

Autenticação como os demais endpoints. Corpo com o JSON do vídeo (precisa de
`slug` e cenas).

```bash
# uma cena, resposta direta (wait só até PREVIEW_SYNC_MAX_SCENES=3 cenas)
curl -X POST $API/previews -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"video": {...}, "scenes": ["cena_02"], "wait": true}'

# vídeo inteiro pela fila → 202 {"job_id": 7, "status": "pending"}
curl -X POST $API/previews ... -d '{"video": {...}, "force": false}'

# status/resultado
curl $API/previews/7 -H "Authorization: Bearer $TOKEN"
# → {"job_id": 7, "status": "done", "result": {...scenes[].path...}, "error": null}

# só assets
curl -X POST $API/previews/prepare ... -d '{"video": {...}}'
```

Execução em subprocesso com o Python do videomaker (`VIDEOMAKER_PYTHON`
sobrescreve a detecção). `PREVIEW_TIMEOUT_S` (default 3600). Como
`app_jobs.config`/`output` são VARCHAR(255), a requisição vai para um arquivo
temporário e o resultado para `previews/result-<job>.json`.
