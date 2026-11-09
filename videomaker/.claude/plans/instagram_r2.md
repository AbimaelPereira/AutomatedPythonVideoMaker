# Plano: Instagram (vídeo + imagem) com R2

## Decisões
- Vídeo → upload resumable direto (sem R2).
- Imagem → JPEG → R2 → `image_url` → apaga do R2.
- Ordem dos uploads: Instagram → YouTube → TikTok.
- Bucket: prefixo `ig/` + Lifecycle Rule de 1 dia (painel R2).
- Credenciais **nunca** no JSON; o JSON só referencia um arquivo de conta.
- Token recomendado: System User (não expira).

Validado em 09/11/2026 na @lojaoprecocaido: reel no feed, story de vídeo
(resumable) e story de imagem (via R2) publicados com sucesso.

## Fase 1 — `libs/R2.py` (já existe, ajustar)
- `upload_file(path, key) -> url` genérico + `delete(key)`.
- Key padrão `ig/{slug}/{arquivo}`.
- `tests/test_r2.py` com boto3 mockado.

## Fase 2 — Contas (`libs/InstagramAccount.py`)
- `"account"` no bloco `instagram` aceita:
  - **nome** → `tokens/instagram_{nome}.json`
  - **caminho** (absoluto, `~`, ou relativo a `videomaker/`) → usa o arquivo direto
  - Mesma regra do `channel_name` (reusar o resolvedor de `libs/utils.py`).
- Formato do arquivo:
  ```json
  { "user_id": "17841...", "token": "EAA...", "username": "lojaoprecocaido" }
  ```
- Alternativa: `"token_env": "NOME_VAR"` no arquivo em vez de `token`
  (vários perfis compartilham um token de System User no `.env`).
- Fallback sem `account`: `IG_USER_ID` / `IG_TOKEN` do `.env`.
- Erro claro se arquivo ausente/campos faltando (no início do render).
- Utilitário: `python -m libs.InstagramAccount --check <account>` →
  `GET /{user_id}?fields=username` + expiração via `debug_token`.

## Fase 3 — `libs/Instagram.py`
- Host `graph.facebook.com/v21.0` (token de Facebook Login).
- Internos: `_create_container`, `_upload_resumable`, `_wait` (poll
  `status_code`, timeout configurável), `_publish -> {id, permalink}`.
- `publish_video(path, targets, caption, ...)`
  - feed → `REELS` (`share_to_feed`, `cover_url`/`thumb_offset` opcionais)
  - story → `STORIES`
- `publish_image(path, targets, caption)`
  - PNG→JPEG (RGB, q95) → R2 → `image_url`; feed `IMAGE`, story `STORIES`
  - `delete` no R2 em `finally`
- `validar()`: caption ≤ 2200 chars, ≤ 30 hashtags; aviso se não 9:16;
  reel 3s–15min; story vídeo ≤ 60s (confirmar comportamento da API);
  imagem ≤ 8MB.
- Targets independentes; retorna lista de resultados.
- `tests/test_instagram.py` com HTTP mockado.

## Fase 4 — Schema JSON
```jsonc
"instagram": {
  "enabled": true,
  "account": "lojao",                    // ou "/caminho/conta.json"
  "targets": ["feed", "story"],
  "caption": "texto #hashtag",
  "share_to_feed": true,
  "cover": { "thumb_offset_ms": 1000 }
}
```
- Mesclado canal < vídeo via `deep_merge`; `account` normalmente no `channels_config`.
- Validado no início do render (como YouTube).

## Fase 5 — `UnifiedVideoEngine`
- Remover o bloco `12a` (R2 genérico) atual.
- Novo passo de upload Instagram antes do YouTube.
- Limpeza (etapa 14): apagar pasta só se **todos** os destinos configurados
  deram certo; senão preserva o MP4.
- Salvar ids/permalinks em `_save_video_record`.

## Fase 6 — Modo imagem
- `"output": { "type": "image" }` (default `"video"`).
- `ImagePostEngine`: Prepare → `PreviewEngine`/`render_frame` por cena →
  `{output}/{slug}/{slug}.png` → `Instagram.publish_image`.
- Pula TTS, legenda, transições, concat, áudio. YouTube/TikTok ignorados com aviso.
- Texto via `text_box`/`visual_elements`; `subtitle`/`motion` → aviso.
- Futuro: várias cenas → `CAROUSEL`.
- Golden test de 1 JSON imagem.

## Fase 7 — API/worker
- Worker inalterado (subprocesso).
- Colunas `instagram_media_ids` (JSON) e `instagram_permalink`.
- Painel: links (opcional).

## Fase 8 — Docs
- `videomaker/.claude/CLAUDE.md`: bloco `instagram`, `account`, `output.type`, envs.
- Skill `pyvideomaker/reference/instagram.md` + `examples/teste_instagram.json`.
- `.env.example`: `R2_*`, `IG_*`.
- Passo a passo do token System User (ver abaixo).

## Fase 9 — Validação
1. `pytest -m "not slow"`
2. Golden render: JSONs legados sem mudança.
3. E2E real: vídeo (feed+story) e imagem (story).

## Token permanente (System User)
1. App em https://business.facebook.com/settings/apps (adicionar app ao Business).
2. Página + conta IG em https://business.facebook.com/settings/pages e
   https://business.facebook.com/settings/instagram-account-assets
3. https://business.facebook.com/settings/system-users → Adicionar → função Admin.
4. "Atribuir ativos": app, Página e conta IG (controle total).
5. "Gerar token": app, expiração **Nunca**, permissões:
   `instagram_basic`, `instagram_content_publish`, `pages_show_list`,
   `pages_read_engagement`, `business_management`.
6. Conferir em https://developers.facebook.com/tools/debug/accesstoken/ → "Expires: Never".
Docs: https://developers.facebook.com/docs/business-management-apis/system-users

## Riscos
- Token de usuário expira ~60 dias → usar System User.
- Limite: 50 publicações/24h por conta.
- Story vídeo > 60s: comportamento da API a confirmar.
