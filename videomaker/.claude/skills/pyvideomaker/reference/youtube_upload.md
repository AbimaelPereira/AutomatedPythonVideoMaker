# Upload (`youtube`)

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

O bloco `youtube` configura o upload automatizado via OAuth, feito por
`YouTube` ([YouTube.py](../../../../libs/YouTube.py)). Tokens ficam em
`tokens/` (não commitar).

```jsonc
"youtube": {
  "title": "Meu vídeo",
  "description": "Descrição completa...",
  "tags": ["tag1", "tag2"],
  "token_file_name": "meu_canal.json",
  "privacy_status": "private",
  "category_id": "22",
  "publish_at": "2026-07-01 18:00:00",
  "timezone": "America/Sao_Paulo",
  "thumbnail": { "type": "ai", "prompt": "..." }
}
```

## Campos

| Campo | Default | Descrição |
|-------|---------|-----------|
| `title` | env `VIDEO_TITLE` | Título do vídeo. |
| `description` | env `VIDEO_DESCRIPTION` | Descrição. |
| `tags` | env `VIDEO_TAGS` (split por vírgula) | Lista de tags. |
| `token_file_name` | `token_default.json` | Arquivo de token OAuth em `tokens/` — geralmente fixo por canal, definido no `channels_config`. |
| `category_id` | `"22"` | Categoria do YouTube (22 = "People & Blogs"). |
| `privacy_status` | `"private"` | `private` / `unlisted` / `public`. |
| `publish_at` | — | Data/hora local (`"YYYY-MM-DD HH:MM:SS"`) para agendar publicação. **Só funciona com `privacy_status: "private"`** — combinação com outro status é ignorada com aviso. |
| `timezone` | `"America/Sao_Paulo"` | Timezone usado para converter `publish_at` para UTC. |
| `thumbnail` | — | Ver seção abaixo. |

## `thumbnail`

```jsonc
// Arquivo fixo
"thumbnail": { "type": "file", "source": "./assets/thumb.png" }

// Sorteia de uma pasta
"thumbnail": { "type": "directory", "source": "./assets/thumbs/" }

// Gera via IA (Pollinations) e salva em output/{slug}/thumbnail.png automaticamente
"thumbnail": {
  "type": "ai",
  "prompt": "descrição da imagem",       // obrigatório
  "provider": "pollinations",             // default
  "model": "flux",                        // default
  "width": 1280, "height": 720,           // defaults
  "quality": "hd",                        // "low"|"medium"|"high"|"hd"
  "seed": 42,                              // opcional, para reproduzibilidade
  "negative_prompt": "...",                // default genérico anti-artefato
  "enhance": false
}
```

A thumbnail gerada por IA é sempre salva em `output/{slug}/thumbnail.png` —
não precisa configurar caminho de saída.

## Autenticação

Primeira execução abre o navegador para o fluxo OAuth (`generate_token`) e
salva o token em `tokens/{token_file_name}`. Execuções seguintes reusam/renovam
o token automaticamente. Variáveis de ambiente (`.env`) podem prover defaults:
`CLIENT_SECRETS_FILE`, `TOKEN_DIR`, `TOKEN_FILE_NAME`, etc.

## Armadilhas frequentes

- **Agendamento (`publish_at`) ignorado** → exige `privacy_status: "private"`;
  com `public`/`unlisted` o agendamento é descartado com aviso no log, mantendo
  a privacidade configurada.
- **Token sempre pedindo novo login** → confira se `token_file_name` está
  fixo no `channels_config` do canal (não mudando por vídeo) — cada nome de
  arquivo gera/usa um token OAuth diferente.
- **Thumbnail IA falha silenciosamente** → exige `thumbnail.prompt`; sem ele,
  loga erro e a thumbnail padrão do YouTube é usada (frame do vídeo).

---

Próximos passos: [channels_config.md](channels_config.md) ·
[estrutura-json.md](estrutura-json.md).
