# Reestruturação do projeto

Resumo da conversa de planejamento (iniciada em 2026-11-26). Branch `reestruturacao`, banco `anonimo_reestruturacao`.

## Objetivo

Separar responsabilidades que hoje estão misturadas no `videomaker`:

- **videomaker** passa a ser só composição e renderização: recebe arquivos já prontos (imagens, vídeos, áudios, timestamps) e um JSON com caminhos, e gera o PNG ou o MP4. Nada de chamar API externa.
- **API nova**, criada do zero pelo usuário (não é adaptar a `api/` atual): tudo que é IA (imagem, vídeo, texto, TTS, transcrição), downloads, remote assets e uploads (YouTube, Instagram, R2, futuramente Pinterest).
- **Banco** no lugar dos JSONs espalhados (channels_config, caches, manifest etc.).

## Ordem de trabalho

1. **Banco primeiro**: definir todas as tabelas (migrations em `database/migrations/`).
2. **Depois a API nova**, já sobre a estrutura do banco definida.

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
- `id`, `uid` (ULID, único, identificador público usado na API), `brand_id`, `title`, `type` (video | image), `status`, `request` (JSON: pedido original inteiro), `settings` (JSON: padrões da marca + pedido, congelados), `output_key` (chave do arquivo final no storage), `error`, `created_at`, `updated_at`

**`app_content_chapters`**: capítulos opcionais do conteúdo.
- `id`, `content_id`, `position` (único por conteúdo), `title`, `settings` (JSON), `status` (pending | rendering | rendered | failed), `error`, `created_at`, `updated_at`

**`app_content_scenes`**: cenas do conteúdo.
- `id`, `content_id`, `chapter_id` (NULL quando não há capítulos), `position` (ordem global no conteúdo, única), `request` (JSON: cena como chegou no pedido), `request_hash`, `resolved` (JSON: cena com arquivos já gerados, entrada do videomaker), `status`, `preview_key`, `video_key`, `error`, `created_at`, `updated_at`

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
- Valores de `status` de conteúdo e cena (proposta: cena `pending → preparing → prepared → previewed → rendered | failed`; conteúdo `draft → preparing → prepared → rendering → rendered → published`).
- Destino das tabelas antigas (`app_remote_assets`, `app_remote_assets_midia`) na estrutura nova.

- Thumbnail (ideia, não decidida): conteúdo `type=image` com `parent_id` apontando para o vídeo; precisa compartilhar os assets do prepare com o conteúdo pai.

### Arquitetura
- O usuário vai explicar como devem funcionar **jobs** e **uploads**.
- Estrutura de endpoints da API nova (a lista anterior foi parcialmente rejeitada).
- Formato do JSON de pedido e do JSON resolvido (contrato entre API e videomaker).
- Modo imagem: o usuário acha a implementação atual gambiarra; redesenhar dentro do fluxo único.
- **Performance do render**: entender os gargalos (vídeos com capítulos ficam lentos) e acelerar sem perder qualidade.

### Ambiente
- MCP `mysql` e `api/.env` apontam para `anonimo` (banco da `main`).
