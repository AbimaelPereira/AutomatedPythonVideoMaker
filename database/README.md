# database

Versionamento do banco MySQL com **Flyway** (via Docker, `flyway/flyway:11.20.0`).
Toda mudança de estrutura (criar/alterar/remover tabela, coluna, índice) é feita **só** por migration aqui. A `api/` não cria tabelas.

## Estrutura

```
database/
├── migrations/              # scripts versionados, aplicados em ordem
│   └── V1__baseline.sql     # estrutura do banco em 2026-11-26
├── backups/                 # dump automático antes de cada migrate (20 últimos, não versionado)
├── flyway.toml              # conexão e config (versionado)
├── flyway.user.toml         # credencial (NÃO versionado)
├── flyway.user.toml.example
├── flyway.sh                # wrapper do Flyway via Docker
└── test-from-zero.sh        # aplica tudo num banco vazio (anonimo_qa) e compara com o anonimo
```

## Banco

- Um só: `anonimo` (MySQL local, `127.0.0.1:3306`).
- Usuário MySQL `anonimo`: tudo em `anonimo` e `anonimo_qa`, nada nos outros bancos do servidor.
- Usado pela `api/.env`, pelo Flyway e pelo MCP `mysql` dos agentes.

## Setup

```bash
cp database/flyway.user.toml.example database/flyway.user.toml   # preencher a senha
./database/flyway.sh info
```

## Criar uma migration

1. Criar arquivo em `migrations/` no padrão `V<AAAAMMDDHHMM>__<descricao>.sql`
   ex.: `V202611261530__adiciona_status_em_app_channels.sql`
2. Aplicar e validar:
   ```bash
   ./database/flyway.sh migrate        # faz backup antes
   ./database/flyway.sh validate
   bash database/test-from-zero.sh
   ```
3. Atualizar o `models.py` correspondente na `api/`.

## Corrigir migration da feature

Vale só para migration que **ainda não está na `main`**:

1. Desfazer no `anonimo` o que ela aplicou (SQL inverso, ex.: `DROP COLUMN`).
2. Apagar o registro dela: `DELETE FROM flyway_schema_history WHERE version = '<versão>';`
3. Editar o arquivo e rodar `./database/flyway.sh migrate` de novo.

Migration já na `main`: **nunca editar**; criar uma nova que corrige.

## Restaurar um backup

```bash
zcat database/backups/anonimo_<data>.sql.gz | mysql -uanonimo -p -h127.0.0.1 anonimo
```

## Regras

- Uma mudança por arquivo, com descrição clara no nome.
- Preferir SQL padrão (evitar `ENUM`, `ON UPDATE CURRENT_TIMESTAMP`, `TINYINT(1)` como bool) para facilitar uma futura migração para Postgres.
- `clean` está desabilitado.

## Comandos úteis

```bash
./database/flyway.sh info       # status das migrations
./database/flyway.sh validate   # arquivos batem com o histórico
./database/flyway.sh repair     # limpa registro de migration que falhou
```
