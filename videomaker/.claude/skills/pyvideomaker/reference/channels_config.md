# Configuração de canal (`channels_config/`)

> Visão geral da estrutura do JSON e ordem de leitura: [../SKILL.md](../SKILL.md).

Cada canal tem um arquivo `channels_config/{channel_name}.json` carregado por
`load_channel_config` ([utils.py](../../../../libs/utils.py)) e mesclado
(`deep_merge`) como a **base** de toda a cadeia — o JSON do vídeo só precisa
declarar o **delta** (o que muda em relação ao canal).

## O que tipicamente vai no `channels_config`

Tudo que se repete em todo vídeo do canal: voz/TTS padrão, estilo de legenda,
fonte/diretório de fundo padrão, transições padrão, dados fixos de upload do
YouTube (categoria, token do canal). Estrutura típica:

```jsonc
{
  "global_settings": {
    "tts": { "provider": "edge", "voice": "pt-BR-AntonioNeural", "pitch": "-40Hz", "rate": "+20%" },
    "subtitle": { "enabled": true, "type": "classic", "font_path": "...", "color": "#1beb0c", "..." : "..." },
    "background": {
      "audio": { "type": "directory", "source": "./assets/audio/background/suspense" },
      "visual": { "fit_mode": "contain-blur", "animation": { "type": "zoom", "duration": 20.0, "intensity": 0.12 } }
    },
    "transitions": { "enabled": true, "audio": { "type": "directory", "source": "./assets/audio/effects/transitions" } }
  },
  "youtube": {
    "token_file_name": "meu_canal.json",
    "privacy_status": "private",
    "category_id": "22"
  }
}
```

Canais reais de referência: `channels_config/hacker_patriota.json` (legenda
estilo "glow" verde), `channels_config/devocional_com_jesus.json`,
`channels_config/broke_to_millionaire.json`, `channels_config/the_touchline_record.json`.

## O que vai no JSON do vídeo, não no canal

- `slug` — único por vídeo.
- `narration.text` de cada cena — conteúdo específico do vídeo.
- `youtube.title` / `description` / `tags` / `publish_at` — específicos do vídeo
  (`token_file_name`/`privacy_status`/`category_id` geralmente ficam no canal,
  pois raramente mudam por vídeo).
- Qualquer override pontual de estilo para um vídeo específico (ex.: uma cor
  de legenda diferente só nesse vídeo) — vai em `global_settings` do próprio
  JSON do vídeo, não no canal.

## Convenção de comentário também vale aqui

Chaves terminadas em `/` são filtradas por `_filter_comment_keys` ao carregar
o canal — útil para manter providers/vozes alternativos desabilitados:

```jsonc
"tts/": { "provider": "local_file", "audio_file": "./temp/geo.wav" }, // ignorado
"tts": { "provider": "edge", "voice": "pt-BR-AntonioNeural" }          // usado
```

## Armadilhas frequentes

- **Canal "não encontrado"** → `load_channel_config` resolve o caminho relativo
  à raiz de `videomaker/` (`channels_config/{channel_name}.json`); confira o
  nome exato do arquivo (sem `.json` no `channel_name`).
- **Override no vídeo não tem efeito** → lembre que listas substituem na
  merge (não fundem); se o canal define uma `palette` de karaokê e o vídeo
  define outra, a do vídeo vence por completo, mesmo que incompleta.

---

Próximos passos: [global_settings.md](global_settings.md) ·
[estrutura-json.md](estrutura-json.md).
