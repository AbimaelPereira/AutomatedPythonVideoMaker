# Estrutura geral do JSON de vídeo

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

O `main.py` aceita um JSON (objeto único ou lista de objetos) e instancia um
`UnifiedVideoEngine` para cada item. Cada objeto de vídeo tem este formato:

```jsonc
{
  "slug": "meu_video",            // nome da pasta/arquivo de saída em output/{slug}/
  "channel_name": "hacker_patriota", // carrega channels_config/{channel_name}.json (base)
  "output": { "ratio": "9:16", "quality": "high" }, // ver output_quality.md
  "global_settings": { /* ... */ },  // ver global_settings.md
  "scenes": [ /* ... */ ],           // OU "chapters" — ver abaixo
  "youtube": { /* ... */ }           // ver youtube_upload.md
}
```

## Campos de topo

| Campo | Obrigatório | Descrição |
|-------|--------------|-----------|
| `slug` | sim | Nome da pasta em `output/{slug}/` e do arquivo final. |
| `channel_name` | sim | Carrega `channels_config/{channel_name}.json` como base via `deep_merge`. Ver [channels_config.md](channels_config.md). |
| `output` | não (default `{"ratio": "9:16", "quality": "high"}`) | Resolução + encoding. Ver [output_quality.md](output_quality.md). |
| `output_ratio` | não | Retrocompat: equivale a `output.ratio` quando solto na raiz. |
| `global_settings` | não | Overrides de `tts`, `subtitle`, `background`, `transitions`, `padding_*`. Ver [global_settings.md](global_settings.md). |
| `scenes` | sim (xor `chapters`) | Lista plana de cenas. Ver [scenes.md](scenes.md). |
| `chapters` | sim (xor `scenes`) | Cenas agrupadas em capítulos, cada um pode sobrescrever `global_settings` e `background.audio`. Ver seção "Capítulos" em [global_settings.md](global_settings.md). |
| `youtube` | não | Configuração de upload. Ver [youtube_upload.md](youtube_upload.md). |

## `scenes` vs `chapters`

São mutuamente exclusivos — o `UnifiedVideoEngine._normalize_scenes` detecta
qual está presente:

- **`scenes`** (lista plana): uso simples, sem trilha de fundo variando por
  seção do vídeo.
- **`chapters`**: cada capítulo agrupa cenas e pode ter seu próprio
  `global_settings` (mesclado por cima do global do vídeo) e seu próprio
  `background.audio` (trilha sonora diferente por seção — ex.: intro calma,
  meio tenso, final aliviado). Os capítulos são "achatados" internamente antes
  do processamento — cada cena resultante carrega de qual capítulo veio.

Detalhes de merge e exemplo completo de `chapters`:
[global_settings.md](global_settings.md#capítulos-chapters).

## Convenção de comentário no JSON

Qualquer chave terminada em `/` (ex.: `"tts/"`) é **silenciosamente ignorada**
pelo pipeline (`_filter_comment_keys` em
[utils.py](../../../../libs/utils.py)). Use para manter configurações
alternativas desabilitadas no próprio arquivo, sem apagar:

```jsonc
"tts/": { "provider": "google", "voice": "pt-BR-Chirp3-HD-Charon" }, // ignorado
"tts": { "provider": "edge", "voice": "pt-BR-AntonioNeural" }         // usado
```

---

Próximos passos: [global_settings.md](global_settings.md) ·
[channels_config.md](channels_config.md) · [scenes.md](scenes.md).
