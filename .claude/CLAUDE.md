# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Visão Geral

Projeto monorepo com três módulos independentes:

- **`api/`** — Backend FastAPI + SQLModel + MySQL. Gerencia canais, vídeos, jobs e autenticação.
- **`videomaker/`** — Motor de geração de vídeos em Python. Roda como CLI ou acionado pela API via fila de jobs.
- **`web/`** — Frontend React + TypeScript + Vite + Tailwind. Painel de controle dos canais.

## Comandos

### API (`api/`)
```bash
# Dentro de api/ com o venv ativado
uvicorn main:app --reload          # dev
uvicorn main:app --host 0.0.0.0    # produção

# Banco: cria tabelas automaticamente no startup (SQLModel.metadata.create_all)
# Seed de canais
python seed_channels.py
```

### Videomaker (`videomaker/`)
```bash
# Setup inicial (instala ffmpeg, ImageMagick, PyTorch e dependências)
bash setup.sh

# Ativar venv e instalar dependências Python
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Gerar vídeo a partir de um JSON
python main.py caminho/para/video.json

# Gerar assets de canal (thumbnails, intro, etc.)
python generate_channel_assets.py
```

### Web (`web/`)
```bash
npm install
npm run dev      # dev (porta 5173)
npm run build    # build de produção
```

## Arquitetura

### API

Cada domínio segue o padrão `módulo/{models,router,service}.py`. O `main.py` registra todos os routers e garante a criação das tabelas via `lifespan`. Configurações lidas de `api/.env` via `pydantic-settings`.

Módulos: `auth`, `admin`, `assets`, `channels`, `videos`, `jobs`, `reelscutter_api`.

Jobs são enfileirados no módulo `jobs/` e processados por um worker (`jobs/worker.py`) que invoca o videomaker como subprocesso.

### Videomaker

Ponto de entrada: `main.py` → lê um JSON (lista ou objeto único) → instancia `UnifiedVideoEngine` para cada item.

**`libs/UnifiedVideoEngine.py`** é o núcleo: orquestra cenas em paralelo via `ProcessPoolExecutor`, monta trilha de áudio, aplica transições, legendas e faz upload.

Camadas principais:
- **`LayoutEngine`** — posicionamento e composição de elementos visuais na cena
- **`VisualClip`** — wrapper de clipes (imagem/vídeo/cor sólida) com transformações
- **`Subtitle`** — geração de legendas com MoviePy/ImageMagick
- **`Background/BackgroundEngine`** — seleção e filtro do vídeo de fundo
- **`Audio/NarrationEngine`** — TTS (Edge-TTS, Google Cloud TTS, AWS Polly) + mixagem
- **`Audio/NarrationEngine` + `Whisper/WhisperWorker`** — transcrição para legendas sincronizadas
- **`AIProviders/`** — abstração sobre Gemini e Pollinations com cache em disco (`AICache`)
- **`Storage/`** — armazenamento local (JSON) e remoto de assets
- **`Transitions/`** — efeitos Fade e Zoom entre cenas
- **`YouTube.py` / `TikTok.py`** — upload automatizado com OAuth (tokens em `tokens/`)

Configs de canal ficam em `channels_config/` e são mescladas (`deep_merge`) com os dados do JSON antes de processar.

### Dependências críticas de versão

> `moviepy==1.0.3` é incompatível com `numpy >= 2.0`. **Não atualize o numpy** sem verificar compatibilidade.
> O `torch` não está no `requirements.txt`; é instalado pelo `setup.sh` de acordo com a versão de CUDA disponível.
> O ImageMagick precisa ter a `policy.xml` ajustada para permitir `TextClip` (feito pelo `setup.sh`).

## Arquivos de Configuração Importantes

| Arquivo | Propósito |
|---|---|
| `api/.env` | Variáveis da API (MySQL, JWT, FRONTEND_URL) |
| `videomaker/channels_config/` | Configs padrão por canal (mescladas com o JSON do vídeo) |
| `videomaker/tokens/` | Tokens OAuth do YouTube/TikTok (não commitar) |
| `videomaker/jsons/` | JSONs de exemplo/produção para geração de vídeos |
