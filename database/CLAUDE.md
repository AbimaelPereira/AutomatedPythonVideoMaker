# database/

- Banco único `anonimo` (MySQL local), usuário `anonimo`. Agentes têm acesso livre (dados e estrutura).
- Flyway via Docker (`./flyway.sh`). Detalhes em `README.md`. Todo `migrate` faz backup antes em `backups/`.
- Migration: `migrations/V<AAAAMMDDHHMM>__<descricao>.sql`, uma mudança por arquivo.
- Migration na `main` é imutável: corrigir com outra. Migration da feature em andamento pode ser editada (ver "Corrigir migration da feature" no README).
- Dados: livre pelo MCP `mysql`. Estrutura (DDL): só por migration.
- Validar: `./flyway.sh validate` + `bash test-from-zero.sh`.
