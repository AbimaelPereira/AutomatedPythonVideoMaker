#!/usr/bin/env bash
# Roda o Flyway via Docker com flyway.toml + flyway.user.toml.
# Uso: ./flyway.sh info | migrate | validate | repair
# Antes de todo `migrate`, salva um dump do banco da branch (schemas do flyway.toml) em database/backups/ (mantém os 20 últimos).
set -euo pipefail
cd "$(dirname "$0")"
DB=$(sed -n 's/^schemas *= *\[ *"\([^"]*\)".*/\1/p' flyway.toml | head -1)

if [[ " $* " == *" migrate "* && " $* " != *"-url="* ]]; then
  mkdir -p backups
  USER_=$(sed -n 's/^user *= *"\(.*\)"/\1/p' flyway.user.toml | head -1)
  F="backups/${DB}_$(date +%Y%m%d_%H%M%S).sql.gz"
  MYSQL_PWD=$(sed -n 's/^password *= *"\(.*\)"/\1/p' flyway.user.toml | head -1) \
    mysqldump -u"$USER_" -h127.0.0.1 --single-transaction --no-tablespaces --set-gtid-purged=OFF "$DB" 2>/dev/null | gzip > "$F"
  echo "backup: database/$F"
  ls -1t backups/"${DB}"_*.sql.gz | tail -n +21 | xargs -r rm --
fi

exec docker run --rm --network host \
  -v "$PWD":/flyway/project -w /flyway/project \
  flyway/flyway:11.20.0 \
  -configFiles=flyway.toml,flyway.user.toml "$@"
