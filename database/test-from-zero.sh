#!/usr/bin/env bash
# Aplica TODAS as migrations num banco vazio temporário (anonimo_qa) e compara a
# estrutura resultante com o banco da branch (schemas do flyway.toml). Garante que as migrations funcionam do zero.
# Sai com código != 0 se a migration falhar ou se a estrutura divergir.
set -euo pipefail
cd "$(dirname "$0")"
DB=$(sed -n 's/^schemas *= *\[ *"\([^"]*\)".*/\1/p' flyway.toml | head -1)

USER_=$(sed -n 's/^user *= *"\(.*\)"/\1/p' flyway.user.toml | head -1)
export MYSQL_PWD=$(sed -n 's/^password *= *"\(.*\)"/\1/p' flyway.user.toml | head -1)
QA=anonimo_qa
M=(mysql -u"$USER_" -h127.0.0.1)

dump() {
  mysqldump -u"$USER_" -h127.0.0.1 --no-data --skip-comments --no-tablespaces \
    --set-gtid-purged=OFF --ignore-table="$1.flyway_schema_history" "$1" 2>/dev/null \
    | sed -E 's/ AUTO_INCREMENT=[0-9]+//; s/ CHARACTER SET utf8mb4//'
}

"${M[@]}" -e "DROP DATABASE IF EXISTS $QA; CREATE DATABASE $QA CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
trap '"${M[@]}" -e "DROP DATABASE IF EXISTS $QA;"' EXIT

./flyway.sh migrate \
  "-url=jdbc:mysql://127.0.0.1:3306/$QA?allowPublicKeyRetrieval=true&useSSL=false" \
  -schemas="$QA" | grep -E "Successfully applied|ERROR" || true

if diff <(dump "$QA") <(dump "$DB"); then
  echo "OK: migrations do zero = estrutura do $DB"
else
  echo "DIVERGENTE: estrutura do zero (<) difere do $DB (>)" >&2
  exit 1
fi
