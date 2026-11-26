# Destinos de upload (`uploads`)

> Visão geral: [../SKILL.md](../SKILL.md). Código: [libs/Uploads.py](../../../../libs/Uploads.py).

Cada chave de `uploads` é um destino. Os destinos presentes recebem o upload, e os ausentes ficam de fora.

```jsonc
"uploads": {
  "youtube":   { "title": "...", "tags": [...], "thumbnail": {...} },   // ver youtube_upload.md
  "instagram": { "targets": ["feed", "story"], "caption": "..." },     // ver instagram.md
  "r2":        { "prefix": "videos/{channel}/{slug}" }
}
```

## Regras

- O `channels_config` e o vídeo podem ter `uploads`. Os dois são mesclados com `deep_merge`, e o vídeo vence.
- Use `"enabled": false` (ou só `false`) para desligar um destino que vem do canal: `"uploads": {"youtube": false}`.
- `"r2": true` ou `"r2": {}` liga o R2 com os defaults. Nos outros destinos, um bloco vazio é ignorado.
- **Formato legado:** `youtube`, `instagram` e `r2` direto na raiz continuam funcionando. Se a mesma chave existir também em `uploads`, ela é mesclada por cima.
- Ordem de envio: Instagram → YouTube → R2.
- A pasta de saída só é apagada se **todos** os destinos derem certo (ver [Limpeza da saída](#limpeza-da-saída)).
- O registro em `app_videos` é salvo se pelo menos um destino publicou.
- Em debug (`DEBUG=1` ou `"debug": true`), nenhum upload é feito.

## Limpeza da saída

Regra: tudo subiu → apaga tudo; algo falhou → guarda só o resultado final.

| Situação | Vídeo | Imagem (`output.type: "image"`) |
|---|---|---|
| Debug (`DEBUG=1` / `"debug": true`) | nada é apagado; `{output}/{slug}/` intacta | nada é apagado |
| Nenhum destino configurado | intermediários apagados; MP4 movido para `{output}/{slug}.mp4`; pasta removida | nada é apagado |
| Todos os destinos OK | `{output}/{slug}/` apagada inteira (MP4 final e cache de assets inclusos) | `{output}/{slug}/` apagada inteira |
| Algum destino falhou | igual a "nenhum destino": só `{output}/{slug}.mp4` sobra, para reenviar sem re-renderizar | só os PNGs finais ficam em `{output}/{slug}/` |

- `{output}` é `output.dir` (default `videomaker/output/`).
- Para guardar uma cópia permanente do vídeo, ligue o `r2`. A pasta local some no sucesso.
- `shutil.rmtree` apaga direto, sem passar pela lixeira.

## Cloudflare R2 (`r2`)

```jsonc
"r2": {
  "prefix": "videos/{channel}/{slug}",  // default
  "video": true,                        // sobe o MP4 final (default true)
  "thumbnail": true                     // sobe a thumbnail gerada no upload do YouTube (default true)
}
```

- Cada arquivo vai para `{prefix}/{nome_do_arquivo}`.
- Variáveis aceitas no `prefix`: `{slug}`, `{channel}`, `{date}` (AAAA-MM-DD), `{year}`, `{month}`.
- O `prefix` **não pode** começar com `ig/`. Esse prefixo é temporário: o lifecycle do bucket apaga os arquivos dele em 1 dia.
- A thumbnail só existe se o YouTube estiver ativo e tiver gerado uma.
- Modo imagem (`output.type: "image"`): sobem todos os PNGs finais.
- Credenciais vêm do `.env`: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_URL`. Elas são validadas antes do render.
- As URLs públicas ficam em `app_videos.r2_files`, no formato `[{"key", "url"}]`.

## Exemplo: YouTube + R2

```jsonc
{
  "slug": "meu_video",
  "channel_name": "meu_canal",
  "uploads": {
    "youtube": { "title": "Meu vídeo", "privacy_status": "private" },
    "r2": { "prefix": "backup/{channel}/{date}" }
  },
  "scenes": [...]
}
```
