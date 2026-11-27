# Reestruturação do projeto

Resumo da conversa de planejamento (iniciada em 2026-11-26). Branch `reestruturacao`, banco `anonimo_reestruturacao`.

## Objetivo

Separar responsabilidades que hoje estão misturadas no `videomaker`:

- **videomaker** passa a ser só composição e renderização: recebe arquivos já prontos (imagens, vídeos, áudios, timestamps) e um JSON com caminhos, e gera o PNG ou o MP4. Nada de chamar API externa.
- **API nova**, criada do zero pelo usuário (não é adaptar a `api/` atual): tudo que é IA (imagem, vídeo, texto, TTS, transcrição), downloads, remote assets e uploads (YouTube, Instagram, R2, futuramente Pinterest).
- **Banco** no lugar dos JSONs espalhados (channels_config, caches, manifest etc.).

## Ordem de trabalho

Meta: o pedido entra na API e sai o MP4 (ou PNG) final. O resto vem depois.

1. **Banco mínimo** já criado (marcas, conteúdos, capítulos, cenas).
2. **Fluxo de ponta a ponta** (fatia vertical mínima):
   1. contrato dos JSONs (`request` e `resolved`);
   2. esqueleto da API nova: `POST /contents` grava conteúdo e cenas (**base pronta**: config, db, models, auth por token, `/health`, `/me`; falta o `POST`, que depende do contrato);
   3. prepare mínimo (1 provedor de imagem, 1 de TTS, storage local);
   4. videomaker lê o `resolved` e gera MP4 por cena e o final;
   5. status a cada etapa + `GET /contents/{uid}`.
3. **Depois**: publicações, registro de IA, demais pendências.

## Como um conteúdo é produzido (visão aprovada pelo usuário)

1. **Pedido chega na API** (vídeo ou imagem).
2. **Prepare** (na API): gera e obtém tudo que o conteúdo precisa.
   - imagens e vídeos de IA, narrações (TTS), elementos visuais (html/icon), remote assets baixados;
   - tudo salvo separado por cena;
   - ao final, gera o JSON resolvido (só caminhos/chaves) para o editor;
   - vale para vídeo e para imagem.
3. **Composição e render** (videomaker):
   - imagem: gera o PNG final;
   - vídeo: preview de baixa qualidade de todas as cenas (rápido) → MP4 de cada cena → MP4 final;
   - tem que ser possível refazer só uma cena (ex.: cena 5) e reconcatenar o vídeo.
4. **Thumbnail** de modo cena é só mais uma imagem gerada pelo pipeline, salva com o conteúdo e depois enviada ao destino.

## Aprovado

### API nova: base
- `api/` antiga apagada na branch (continua na `main`); recriada do zero no mesmo lugar.
- Python 3.12 via `uv`, FastAPI, **SQLAlchemy 2.0** (no lugar do SQLModel), pymysql síncrono. Models só mapeiam as tabelas do Flyway.
- Estrutura por domínio: `app/core` (config, db, auth, security), `app/{brands,users,contents,jobs}`, `worker/`, `tests/`.
- Auth: `Authorization: Bearer <token>` de `app_api_tokens` (sha256); token = 1 usuário + 1 marca. Criação via `uv run python -m app.cli create-token`.
- Testes no banco da branch, dentro de transação desfeita no fim.
- `api/.env` só com `MYSQL_*` e `ENVIRONMENT` (JWT e `FRONTEND_URL` removidos).

### Motor de vídeo: tudo via FFmpeg
- O videomaker novo renderiza **tudo** por filtergraph do FFmpeg (`filter_complex`): fundo, zoom/pan, overlays, fade/transições, motion e áudio. Legendas em `.ass` (libass).
- **Sem MoviePy** e sem composição frame a frame em Python/numpy. Elemento que o FFmpeg não faz direto é pré-renderizado (PNG ou vídeo com alpha) e entra como overlay.
- Motivo (benchmark de 2026-11-27, cena de 18s em 1080p): render da cena levou ~27s pelo FFmpeg e ~155s pelo MoviePy.
- Linguagem continua Python: o ganho vem do FFmpeg, não da linguagem.
- **Um encode só**: cada cena já sai no formato final (codec, resolução, fps, preset) e o vídeo final é concatenado com `-c copy`, sem reencode. Hoje há dois encodes (cena em `ultrafast` crf12 + reencode final em `slow` crf18, ~25s a cada 18s de vídeo).

### Motor de vídeo e motor de áudio separados
1. **Timeline** primeiro: a duração de cada cena vem da narração; os dois motores leem os mesmos tempos.
2. **Motor de vídeo**: MP4 de cada cena **sem áudio** → concat com `-c copy`.
3. **Motor de áudio**: narração + música de fundo + SFX numa faixa só, com normalização de volume uma vez no vídeo inteiro.
4. **Mux** final: `-c:v copy -c:a aac` (segundos).
- Trocar música/volume refaz só áudio + mux; refazer uma cena refaz só ela + concat + mux. Os motores podem rodar em paralelo.
- Cuidados: duração de cada cena em frames inteiros (ex.: 538 frames a 30fps) e o áudio seguindo a mesma duração, senão a legenda escorrega; narração mudou → vídeo da cena também é refeito; SFX ligados ao visual (ex.: whoosh na transição) são eventos da timeline; preview de cena com som = mux da cena com o trecho dela do áudio.

### Divisão de responsabilidades
- TTS vai para a API como IA: endpoint tipo `/ai/tts`.
- Whisper vai para a API com endpoint próprio de transcrição, e também como etapa opcional dentro do TTS (para provedores que não geram timestamps por palavra) e para narração já gravada.
- Elementos `html/icon` (Chromium) e `SilenceRemover` ficam na API (parte do prepare); o videomaker recebe os arquivos já gerados.

### Limpezas já feitas (commit e push)
- `videomaker/reelscutter/` removido, junto com `yt-dlp` e `youtube-transcript-api` do `requirements.txt`.
- `videomaker/prompts/` e `videomaker/development/` removidos.
- Regra "toda migration ajusta o `models.py` da api" removida de `database/CLAUDE.md`, `database/README.md` e do agente `db-migration`. Models criados em `api/brands/` removidos.

### Branches e bancos
- `main` resetada para `b611a40` (force push) e usa o banco `anonimo`, restaurado ao estado desse commit.
- `reestruturacao` tem todo o trabalho novo e usa o banco `anonimo_reestruturacao` (definido no `database/flyway.toml` da branch).

### Tabelas criadas (migrations aplicadas)

**`app_brands`**: marca que publica conteúdo, com os padrões de criação.
- `id`, `slug` (único), `name`, `description`, `defaults` (JSON), `is_active`, `created_at`, `updated_at`

**`app_brand_account_youtube`**: canal do YouTube da marca.
- `id`, `brand_id`, `channel_id` (único), `channel_title`, `access_token`, `refresh_token`, `token_expires_at`, `default_privacy`, `default_category_id`, `is_active`, `created_at`, `updated_at`

**`app_brand_account_instagram`**: conta do Instagram da marca.
- `id`, `brand_id`, `ig_user_id` (único), `username`, `access_token`, `token_expires_at`, `is_active`, `created_at`, `updated_at`

**`app_contents`**: um vídeo ou uma imagem da marca.
- `id`, `uid` (ULID, único, identificador público usado na API), `brand_id`, `title`, `type` (video | image), `status` (queued | preparing | prepared | rendering | rendered | failed), `request` (JSON: pedido original inteiro), `settings` (JSON: padrões da marca + pedido, congelados), `video_key` (cenas concatenadas sem áudio), `audio_key` (faixa final: narração + música + SFX), `output_key` (chave do arquivo final no storage; mux de vídeo + áudio), `error`, `created_at`, `updated_at`

**`app_content_chapters`**: capítulos opcionais do conteúdo.
- `id`, `content_id`, `position` (único por conteúdo), `title`, `settings` (JSON: ex.: música própria do capítulo), `created_at`, `updated_at`

**`app_content_scenes`**: cenas do conteúdo.
- `id`, `content_id`, `chapter_id` (NULL quando não há capítulos), `position` (ordem global no conteúdo, única), `request` (JSON: cena como chegou no pedido), `request_hash`, `resolved` (JSON: cena com arquivos já gerados, entrada do videomaker), `status` (pending | preparing | prepared | previewed | rendering | rendered | failed), `preview_key` (PNG rápido de baixa qualidade, para revisar antes do render), `output_key` (MP4 da cena sem áudio, ou PNG se imagem), `preview_ms`, `render_ms` (tempo em ms de cada etapa), `error`, `created_at`, `updated_at`

**`app_jobs`**: fila de tarefas lida pelo worker (processo Python rodando em loop, separado da API).
- `id`, `content_id`, `scene_id` (NULL = conteúdo inteiro), `type` (prepare | preview | render_video | render_audio | concat_video | mux | render_image), `status` (pending | running | done | failed), `attempts`, `error`, `started_at`, `finished_at`, `created_at`, `updated_at`
- Fluxo: ver "Jobs do conteúdo" abaixo.

### Jobs do conteúdo
`type` diz a etapa; `scene_id` diz o escopo (cena ou conteúdo inteiro). Vídeo com 10 cenas:

| Ordem | `type` | Escopo | Qtd | Pode começar quando |
|---|---|---|---|---|
| 1 | `prepare` | cena | 10 | o pedido chegar |
| 2 | `preview` | cena | 10 | `prepare` da mesma cena terminar (só se o pedido pedir preview) |
| 3 | `render_video` | cena | 10 | `prepare` da mesma cena terminar |
| 4 | `render_audio` | conteúdo | 1 | todos os `prepare` terminarem (precisa das durações) |
| 5 | `concat_video` | conteúdo | 1 | todos os `render_video` terminarem |
| 6 | `mux` | conteúdo | 1 | `concat_video` e `render_audio` terminarem |

- Imagem: `prepare` → `render_image`.
- A API cria o plano inteiro como `pending` quando o pedido chega; o usuário vê tudo desde o início.
- O worker só pega um job quando as dependências da coluna "Pode começar quando" terminaram. Regra no código, sem coluna nova.
- Refazer a cena 5: recria `prepare`(5), `render_video`(5), `render_audio`, `concat_video`, `mux`. Mudou motion/SFX da cena: idem (áudio inteiro é remixado, custa segundos; sem `audio_key` na cena).
- Status derivados dos jobs. Conteúdo: `queued` → `preparing` → `prepared` → `rendering` → `rendered` (ou `failed`). Cena: `pending` → `preparing` → `prepared` → `previewed` → `rendering` → `rendered` (ou `failed`). Publicação tem status próprio (tabela futura), não fica no conteúdo.
- Capítulo é só agrupamento (título + `settings`, ex.: música própria); não tem status nem render. O `render_audio` lê o `settings` de cada capítulo.

`GET /contents/{uid}` (etapas sempre na mesma ordem, com contagem):

```json
{
  "uid": "01JD...",
  "status": "rendering",
  "progress": { "done": 17, "total": 33 },
  "steps": [
    { "step": "prepare",      "status": "done",    "done": 10, "total": 10 },
    { "step": "render_video", "status": "running", "done": 4,  "total": 10 },
    { "step": "render_audio", "status": "done",    "done": 1,  "total": 1 },
    { "step": "concat_video", "status": "pending", "done": 0,  "total": 1 },
    { "step": "mux",          "status": "pending", "done": 0,  "total": 1 }
  ],
  "scenes": [
    { "position": 1, "prepare": "done", "render_video": "done",   "error": null },
    { "position": 5, "prepare": "done", "render_video": "failed", "error": "..." }
  ],
  "output_key": null
}
```

### Decisões de modelagem
- Padrão de nome `app_brand_account_{integração}`: uma tabela por plataforma.
- `app_contents` usa `uid` (ULID) e não `slug`.
- Nada de caminho absoluto no banco: só **chaves de storage** (`contents/{uid}/scenes/05/preview.png`). Um driver (`STORAGE=local|r2|s3`) resolve a chave; o videomaker trabalha numa pasta temporária, baixa insumos, renderiza e sobe o resultado.
- `output_key` mantido como coluna (não derivado do `uid`).
- Capítulos são opcionais: short só tem cenas; vídeo longo pode ter capítulos com cenas dentro. Sem mistura no mesmo conteúdo (a API valida).
- Ordem de mesclagem: `brand.defaults` → `content.settings` → `chapter.settings` → `scene.request`.
- Refazer uma cena: muda o `request` → muda o `request_hash` → prepare e render só daquela cena → reconcatena.
- `status` e `type` como texto (sem enum); a API valida.
- Marca não é apagada (FK sem cascade em `app_contents` bloqueia); desativar com `is_active = 0`.
- Cena só aponta para capítulo do mesmo conteúdo: FK composta `(chapter_id, content_id)` garante no banco.
- `position` da cena é fixo por enquanto (sem reordenação).
- Timestamps por palavra ficam dentro do `resolved` da cena (sem tabela de transcrições).

## Rejeitado ou criticado pelo usuário

- **Não mexer na `api/` atual.** A API será nova; nada de criar models ou código lá.
- **Não se basear no que existe hoje.** É estrutura nova e melhor, sem coisas não usadas.
- **Nada de JSON espalhado em arquivos**: usar o banco.
- Primeiro fluxo de vídeo proposto: estava errado (o fluxo correto é o descrito acima).
- Propostas de `jobs/` e `uploads/` como apresentadas: não gostou.
- Endpoints `prepare/`, `render/`, `channels/`, `credentials/` na lista da nova API: discordou.
- Nome `channel` / `app_channels`: passa a ideia de que é só YouTube. Trocado por `app_brands`.
- Nome `productions` / `app_productions`: soou estranho. Trocado por `app_contents`.
- Tabela única `app_accounts` com `platform`: preferiu uma tabela por integração.
- Tabela `app_files`: não viu sentido.
- `dir`, `thumbnail_path` e `duration` em `app_contents`: fora por enquanto.

## Pendente (ainda não revisado nem aprovado)

### Banco
- Tabela(s) de **uploads/publicações** (YouTube, Instagram, R2, Pinterest): título, descrição e tags por plataforma, status, id externo, URL.
- Armazenamento do **R2/object storage**: não é conta da marca; decidir se é tabela própria ou só `.env`.
- **Criptografia de tokens** nas tabelas de conta (chave no `.env`?).
- Marca com mais de um canal/conta por plataforma: hoje 1:N, sem `UNIQUE (brand_id)`.
- Registro de **chamadas de IA** (provedor, modelo, parâmetros, custo, cache por hash): proposto como `app_ai_generations`, não revisado.
- Registro de **execuções de render** para medir gargalos: proposto como `app_render_runs`, não revisado.
- `video_key` no capítulo (mp4 por capítulo com áudio de fundo mixado; final = concat dos capítulos).
- Caches que hoje são JSON no videomaker (`media_probe`, `directory_usage`, `remote_assets`): decidir se vão para o banco ou se o videomaker recebe tudo pronto e fica sem banco.
- Destino das tabelas antigas (`app_remote_assets`, `app_remote_assets_midia`) na estrutura nova.

- Thumbnail (ideia, não decidida): conteúdo `type=image` com `parent_id` apontando para o vídeo; precisa compartilhar os assets do prepare com o conteúdo pai.

### Arquitetura
- O usuário vai explicar como devem funcionar **jobs** e **uploads**.
- Estrutura de endpoints da API nova (a lista anterior foi parcialmente rejeitada).
- Formato do JSON de pedido e do JSON resolvido (contrato entre API e videomaker).
- Modo imagem: o usuário acha a implementação atual gambiarra; redesenhar dentro do fluxo único.
- **Performance do render**: entender os gargalos (vídeos com capítulos ficam lentos) e acelerar sem perder qualidade.

### Ambiente
- MCP `mysql` aponta para `anonimo` (banco da `main`); usar `anonimo_reestruturacao.<tabela>`. `api/.env` já aponta para `anonimo_reestruturacao`.
