# api/

API nova da reestruturação (ver `docs/reestruturacao.md`). FastAPI + SQLAlchemy 2.0 + MySQL, Python 3.12 via `uv`.

- Ambiente: `uv sync` · testes: `uv run pytest` · dev: `uv run uvicorn app.main:app --reload`.
- Estrutura por domínio em `app/<domínio>/{models,schemas,router,service}.py`; `app/core/` tem config, db, auth e segurança. `worker/` é o processo que consome `app_jobs`.
- Models só **mapeiam** tabelas: estrutura do banco é só via Flyway (`database/`). Nada de `create_all`. Mudou o banco → ajustar o model correspondente.
- Auth: `Authorization: Bearer <token>` de `app_api_tokens` (compara sha256). Cada token = 1 usuário + 1 marca (`CurrentPrincipal`). Criar token: `uv run python -m app.cli create-token --email ... --brand <slug>`.
- Config em `app/core/config.py` (lê `.env`: `MYSQL_HOST/PORT/USER/PASS/DBNAME`). Nunca commitar `.env`. Nesta branch `MYSQL_DBNAME=anonimo_reestruturacao`.
- Testes usam o banco da branch (lido de `database/flyway.toml`) dentro de transação desfeita no fim: nada fica gravado.
