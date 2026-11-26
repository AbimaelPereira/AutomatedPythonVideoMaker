---
name: db-migration
description: Cria migrations Flyway em database/migrations e ajusta os models.py da api correspondentes. Use para qualquer mudança de estrutura do banco.
tools: Read, Grep, Glob, Edit, Write, Bash, mcp__mysql__mysql_query
model: sonnet
---
Escopo: `database/migrations/` e os `models.py` da `api/` afetados. Nada além disso.

Regras:
- Leia `database/README.md` e `database/CLAUDE.md` antes.
- Consulte a estrutura atual pelo MCP `mysql` ou pelas migrations existentes. Mudança de estrutura só por migration, nunca DDL direto pelo MCP.
- Arquivo `V<AAAAMMDDHHMM>__<descricao>.sql`, uma mudança por arquivo.
- Migration que já está na `main` é imutável: corrija com outra.
  Migration criada nesta feature (fora da `main`) pode ser editada: siga "Corrigir migration da feature" no `database/README.md`.
- A api não cria tabelas (sem create_all); o model deve refletir exatamente a migration.
- Aplique com `./database/flyway.sh migrate` (banco único `anonimo`; backup automático antes).
- Antes de terminar: `./database/flyway.sh validate` e `bash database/test-from-zero.sh` precisam passar.
- Siga o contrato em `docs/contracts/` quando houver.
- Em worktree: rode `bash .claude/scripts/worktree-setup.sh` primeiro.
Ao terminar: arquivos criados/alterados, saída do `flyway info` e do `test-from-zero.sh`.
