# CLAUDE.md

Monorepo com três módulos independentes. Cada um tem seu CLAUDE.md com comandos e regras — **leia o do módulo antes de mexer nele**.

| Módulo | O que é | Instruções |
|---|---|---|
| `api/` | Backend FastAPI + SQLModel + MySQL (remote assets) | `api/CLAUDE.md` |
| `videomaker/` | Motor de geração de vídeos (CLI) | `videomaker/.claude/CLAUDE.md` |
| `database/` | Migrations Flyway do MySQL (dono da estrutura do banco) | `database/CLAUDE.md` |

## Como os módulos conversam

- `api` → MySQL (só dados; a estrutura é do `database/`).
- `videomaker` → `api` (remote assets, header `X-Service-Token`).

## Banco

- Um banco por branch (MySQL local): `main` → `anonimo`, `reestruturacao` → `anonimo_reestruturacao` (ver `database/flyway.toml`). Agentes têm acesso livre: dados pelo MCP `mysql`, estrutura só por migration em `database/migrations/` (nada de `create_all`).
- Todo `./database/flyway.sh migrate` faz backup antes em `database/backups/`.

## Agentes e fluxo de feature

- `/feature <descrição>`: `planner` → `db-migration` → `api-dev` / `videomaker-dev` (worktrees, em paralelo) → `qa`. Ver `.claude/skills/feature/SKILL.md`.
- Agentes em `.claude/agents/`; contratos entre módulos em `docs/contracts/`.
- Em worktree: `bash .claude/scripts/worktree-setup.sh` (liga venvs, `.env`, assets do repo principal).
- `.claude/settings.json`: bloqueia edição dos `.env` e leitura de `tokens/`.

## Segredos (não commitar)

`api/.env`, `videomaker/.env`, `videomaker/tokens/`, `database/flyway.user.toml`, `database/backups/`.
