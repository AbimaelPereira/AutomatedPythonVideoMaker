# Instagram (`instagram`) e modo imagem

```jsonc
"instagram": {
  "enabled": true,                       // default true se o bloco existe
  "credentials_json": "/caminho/instagram.json",  // só caminho (abs, ~ ou relativo a videomaker/)
  "targets": ["feed", "story"],          // feed: REELS (vídeo) / IMAGE • story: STORIES
  "caption": "texto #hashtag",           // ≤ 2200 chars, ≤ 30 hashtags (story ignora)
  "share_to_feed": true,                 // reels
  "cover": { "thumb_offset_ms": 1000 }   // ou { "url": "https://..." }
}
```

- Canal < vídeo via `deep_merge`. Coloque `credentials_json` no `channels_config`.
- `credentials_json` obrigatório (sem atalho por nome). Arquivo da conta (nunca no JSON do vídeo): `{"user_id": "...", "token": "..."}`.
  Nada vem do `.env`. Sem bloco `instagram` no vídeo/canal → não publica.
- Checar: `python -m libs.InstagramAccount --check /caminho/instagram.json`.
- Validado antes do render: targets, caption, hashtags. Reel 3s–15min. Aviso se não 9:16.
- Upload antes do YouTube. Pasta de saída só é apagada se todos os destinos deram certo.
- Limite da API: 50 publicações/24h por conta.

## Modo imagem

`"output": { "type": "image" }` → cada cena vira um PNG (pose de repouso, motor do preview)
em `{output}/{slug}/{slug}[_NN].png`, publicado via R2. Sem TTS/legenda/áudio/transições.
- 1 cena → post (feed) / story. 2–10 cenas → **carrossel** no feed; no story, um story por imagem, em ordem.
- Caption só no feed. > 10 cenas com `feed` → erro antes do render.
- Tudo OK → apaga a pasta. Falha → mantém só os PNGs finais.
Texto: `visual_elements` `text_box`. `youtube`/`tiktok` ignorados.
Exemplo: `examples/teste_instagram.json`.
