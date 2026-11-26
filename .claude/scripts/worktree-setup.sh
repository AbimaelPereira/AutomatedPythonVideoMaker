#!/usr/bin/env bash
# Cria symlinks, dentro de um git worktree, para os arquivos ignorados pelo git que
# existem no repo principal (venvs, .env, node_modules, assets, flyway.user.toml...).
# Sem isso, pytest / npm run build / flyway.sh falham no worktree.
# Uso (dentro do worktree): bash .claude/scripts/worktree-setup.sh
set -euo pipefail

WT=$(git rev-parse --show-toplevel)
MAIN=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")

if [[ "$WT" == "$MAIN" ]]; then
  echo "Não é um worktree (já está no repo principal). Nada a fazer."
  exit 0
fi

# Ignorados que NÃO devem ser compartilhados (estado de execução / lixo)
SKIP='(__pycache__|\.pytest_cache|^\.claude/projects/|/output/|/temp/|/cache/|\.claude/worktrees/)'

n=0
while IFS= read -r rel; do
  rel=${rel%/}
  [[ -z "$rel" || "$rel" =~ $SKIP ]] && continue
  [[ -e "$WT/$rel" || -L "$WT/$rel" ]] && continue
  mkdir -p "$(dirname "$WT/$rel")"
  ln -s "$MAIN/$rel" "$WT/$rel"
  n=$((n+1))
done < <(git -C "$MAIN" ls-files --others --ignored --exclude-standard --directory)

echo "worktree-setup: $n links criados a partir de $MAIN"
