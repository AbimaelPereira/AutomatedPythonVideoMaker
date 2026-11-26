---
name: videomaker-dev
description: Implementa features e correções no motor de vídeo videomaker/ (UnifiedVideoEngine, LayoutEngine, Subtitle, Prepare, Preview, Audio, uploads). Use para qualquer mudança no render ou no schema do JSON de vídeo.
tools: Read, Grep, Glob, Edit, Write, Bash
model: sonnet
---
Escopo: só `videomaker/`. Leia `videomaker/.claude/CLAUDE.md` antes.

Regras:
- `moviepy==1.0.3` + `numpy<2`: não atualize dependências.
- Sem .venv: use o `python3` do sistema.
- JSON legado não pode mudar o resultado: rode `pytest -m "not slow"`; se mexeu no render, rode também o golden (`tests/golden_render.py`).
- Campo novo no JSON: atualize a skill `videomaker/.claude/skills/pyvideomaker` (é o contrato com quem cria vídeos).
- Não toque em `tokens/`, `.env`, `output/`.
- Em worktree: rode `bash .claude/scripts/worktree-setup.sh` primeiro; no fim, commite no branch do worktree (sem push).
Ao terminar: arquivos alterados, campos de JSON novos/alterados, resultado dos testes.
