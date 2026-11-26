# api/

- FastAPI + SQLModel + MySQL. Venv em `api/.venv`; testes: `.venv/bin/pytest` (marker `slow` renderiza de verdade).
- Cada domínio: `módulo/{models,router,service}.py`; routers registrados em `main.py`.
- Estrutura do banco é só via Flyway (`database/`). A api não cria nem altera tabelas.
- Config via `config.py` (pydantic-settings, lê `.env`). Nunca commitar `.env` nem `tokens/`.
- Jobs: enfileirados em `jobs/`, processados por `jobs/worker.py`, que chama o videomaker como subprocesso.
- Módulos: `auth`, `admin`, `assets`, `channels`, `videos`, `jobs`, `reelscutter_api`, `previews`, `subtitle_preview`, `thumbnail_preview`, `youtube`, `ai_generation`.
- Rodar: `.venv/bin/uvicorn main:app --reload` (dev) · `--host 0.0.0.0` (produção). Seed de canais: `.venv/bin/python seed_channels.py`.
- `.env` aponta para o banco `anonimo` (usuário MySQL `anonimo`).
