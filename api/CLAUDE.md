# api/

- FastAPI + SQLModel + MySQL. Venv em `api/.venv`.
- Cada domínio: `módulo/{models,router,service}.py`; routers registrados em `main.py`.
- Estrutura do banco é só via Flyway (`database/`). A api não cria nem altera tabelas.
- Config via `config.py` (pydantic-settings, lê `.env`). Nunca commitar `.env`.
- Módulos: `assets` (remote assets). Toda rota exige header `X-Service-Token` (`middleware/auth.py`); não há login de usuário.
- Rodar: `.venv/bin/uvicorn main:app --reload` (dev) · `--host 0.0.0.0` (produção).
- `.env` aponta para o banco `anonimo` (usuário MySQL `anonimo`).
