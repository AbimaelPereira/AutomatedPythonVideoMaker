# CLAUDE.md

Este arquivo fornece orientações ao Claude Code (claude.ai/code) ao trabalhar com o código deste repositório.

## O que este projeto faz

Automated Python Video Maker: gera vídeos curtos/longos para o YouTube a partir de uma especificação JSON. Cada JSON descreve cenas com narração (TTS), visuais de fundo, legendas, transições e upload opcional para o YouTube.

## Executando o projeto

```bash
# Gera um vídeo a partir de um arquivo JSON (pode ser uma lista de objetos de vídeo)
python main.py jsons/hacker_patriota.json

# Modo debug (pula o upload para o YouTube e abre o vídeo localmente)
DEBUG=1 python main.py jsons/myjson.json

# Controla o paralelismo (padrão: 2 workers)
MAX_PARALLEL_SCENES=4 python main.py jsons/myjson.json
```

Não há suítes de testes. Os testes são feitos manualmente executando `main.py` com um arquivo JSON.

## Estrutura do JSON

Cada objeto de vídeo possui:
- `slug` — nome do arquivo de saída e da pasta dentro de `output/`
- `channel_name` — carrega `channels_config/{channel_name}.json` como configuração base (mesclado via `deep_merge`)
- `output_ratio` — `"9:16"` (1080×1920) ou `"16:9"` (1920×1080)
- `global_settings` — sobrescreve os padrões do canal: `tts`, `subtitle`, `background`, `transitions`, `padding_*`, `remote_assets`
- `scenes` (lista plana) OU `chapters` (agrupado; cada capítulo pode sobrescrever `global_settings` e `background.audio`)
- `youtube` — title, description, tags, `token_file_name`, `privacy_status`, `publish_at`

**Convenção de comentário no JSON**: qualquer chave terminada com `/` (ex: `"tts/"`) é silenciosamente ignorada por `_filter_comment_keys`. Use isso para manter configurações desabilitadas ou alternativas no arquivo.

### Campos de cena
```json
{
  "id": "cena_01",
  "narration": { "text": "...", "subtitles": true },
  "duration": 5.0,          // opcional; padrão é a duração do TTS
  "background": { "visual": {...}, "audio": {...} },
  "visual_elements": [...], // imagens/vídeos sobrepostos posicionados pelo LayoutEngine
  "transitions": { "enabled": false },  // sobrescreve transições globais por cena
  "tts": { "provider": "edge" },        // sobrescreve o provider TTS por cena
  "subtitle": { "font_size": 90 }       // sobrescreve o estilo das legendas por cena
}
```

### Tipos de visual de fundo
- `"type": "directory"` — escolhe um arquivo aleatório de uma pasta
- `"type": "file"` — caminho para um arquivo único
- `"type": "remote_asset"` — resolve um slug via `RemoteAssetManager` (lê `cache/remote_assets.json`)
- `"type": "ai"` — gera uma imagem/vídeo via `libs/AIProviders` (Pollinations)

### Providers de TTS
- `"edge"` — Microsoft Edge TTS (gratuito, sem credenciais)
- `"google"` — Google Cloud TTS (requer `credentials_file`)
- `"polly"` — AWS Polly
- `"local_file"` — usa um arquivo de áudio pré-gravado (aciona segmentação via Whisper)

## Arquitetura

```
main.py
  └── UnifiedVideoEngine          # orquestra todo o pipeline
        ├── NarrationEngine       # síntese TTS + alinhamento de legendas via Whisper
        │     ├── TTS_Edge / TTS_GoogleCloud / TTS_Polly
        │     ├── SilenceRemover  # remoção de silêncios via pydub
        │     └── AudioSegmenter  # divide arquivos de áudio locais longos
        ├── BackgroundEngine      # monta o clipe de fundo (vídeo/imagem/IA)
        │     ├── DirectoryType   # escolhe arquivo aleatório do diretório
        │     └── FiltersEngine   # animações zoom e contain-blur
        ├── VisualClip            # processa overlays de visual_elements
        ├── LayoutEngine          # posiciona/redimensiona elementos visuais (stack ou explícito)
        ├── Subtitle              # renderiza legendas SRT como clipes MoviePy
        ├── TransitionEngine      # transições fade/zoom nas cenas
        │     ├── Fade / Zoom
        │     └── TransitionUtils
        ├── RemoteAssetManager    # resolve slug→URL e faz cache em disco
        │     └── Storage/        # JSONAssetStorage, RemoteAssetStorage
        ├── AIProviders           # geração de imagens (Pollinations)
        │     └── AICache         # faz cache das imagens geradas em cache/ai_generated/
        ├── MediaDownloader       # baixa vídeos/imagens remotos para temp/
        └── YouTube               # faz upload do MP4 final e define a thumbnail
```

**Processamento de cenas**: cada cena é processada de forma independente (sequencial ou em paralelo via `ProcessPoolExecutor`). Após todas as cenas renderizarem em MP4s individuais, elas são concatenadas via FFmpeg e o áudio de fundo é misturado.

**Ordem de mesclagem de configurações** (itens abaixo sobrescrevem os acima):
1. Config do canal (`channels_config/{channel_name}.json`)
2. `global_settings` do vídeo
3. `global_settings` do capítulo (se usar chapters)
4. Sobrescritas por cena (`tts`, `subtitle`, `transitions`)

Todas as mesclagens usam `deep_merge` de `libs/utils.py` — dicts aninhados são mesclados recursivamente, não substituídos.

## Detalhes importantes

- **Saída**: os arquivos renderizados vão para `output/{slug}/`. Após uma execução bem-sucedida fora do modo debug, os arquivos intermediários são removidos; se o upload para o YouTube estiver configurado, a pasta de saída inteira é deletada após o upload.
- **Whisper**: fica em `libs/Whisper/` com seu próprio virtualenv (`venv-whisper`). Usado apenas com o provider `local_file` para alinhamento de legendas.
- **Cache de remote assets**: `cache/remote_assets.json` mapeia slugs para URLs de mídia. `RemoteAssetManager` valida as URLs e as marca como válidas/inválidas.
- **Credenciais**: tokens OAuth do YouTube em `tokens/`, chave JSON do Google Cloud TTS também em `tokens/`. O arquivo `.env` pode conter segredos adicionais.
- **Paralelismo**: a variável de ambiente `MAX_PARALLEL_SCENES` controla os workers; cai automaticamente para 1 se a RAM disponível for menor que 4 GB.
