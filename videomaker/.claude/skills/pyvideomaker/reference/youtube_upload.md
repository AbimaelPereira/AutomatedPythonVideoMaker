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

### `type: "scene"` — thumbnail composta

Monta a thumbnail como uma **cena de 1 frame**: aceita o mesmo `background` e os
mesmos `visual_elements` de uma cena do vídeo, com o mesmo `placement`. É o modo
para combinar fundo (IA/imagem) com caixa de texto, degradê e logo.

```jsonc
"thumbnail": {
  "type": "scene",
  "width": 1280, "height": 720,          // defaults (padrão YouTube)

  "background": {
    "visual": { "type": "ai", "prompt": "dark cathedral, cinematic light" }
  },

  "visual_elements": [
    // Degradê para escurecer só a faixa do texto, sem apagar a imagem
    { "type": "gradient", "direction": "to_top",
      "stops": [ { "color": "#000000", "opacity": 0.9, "at": 0.0 },
                 { "color": "#000000", "opacity": 0.0, "at": 0.6 } ],
      "placement": { "anchor": ["center","center"], "width": "100%",
                     "height": "100%", "relative_to": "screen" } },

    { "type": "text_box", "content": "ELE NUNCA\nTE ABANDONOU",
      "style": { "font_path": "./assets/fonts/Montserrat/Montserrat-Black.ttf",
                 "font_size": 96, "text_color": "#FFE24A",
                 "background_color": "transparent",
                 "stroke_color": "#000000", "stroke_width": 8,
                 "shadow": { "offset": [6,6], "color": "#000000",
                             "blur": 4, "opacity": 0.8 },
                 "line_spacing": 1.05, "align": "left" },
      "placement": { "anchor": ["left","bottom"], "width": "62%" } }
  ]
}
```

| Campo | Default | Descrição |
|-------|---------|-----------|
| `width` / `height` | `1280` / `720` | Resolução da thumbnail (independente do `output.ratio` do vídeo). |
| `background` | herda o global | Mesmos tipos de `background.visual` de uma cena (`ai`, `image`, `color`, `video`, `directory`, `remote_asset`). Omitido → herda o fundo do canal/vídeo. |
| `visual_elements` | `[]` | Mesmos tipos de overlay de uma cena, incluindo `gradient` e `text_box`. |
| `padding_*` | por orientação | Área segura da thumbnail. Os paddings do canal só são herdados se a orientação for a mesma do vídeo (um `padding_bottom: 850` de 9:16 colapsaria uma thumb 16:9). |

Salva em `output/{slug}/thumbnail.png`, como os demais tipos. Se o PNG passar de
2MB (limite do YouTube), é recomprimido em JPEG automaticamente.

> Para um overlay que cobre a tela inteira, use
> `"relative_to": "screen"` no `placement` — sem ele, `width: "100%"` significa
> 100% da **área segura**, deixando a moldura do padding aparecendo.

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
