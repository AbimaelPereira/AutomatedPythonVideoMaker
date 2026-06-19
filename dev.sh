#!/usr/bin/env bash
#
# Sobe a API (FastAPI/uvicorn) e o frontend web (Vite) juntos para desenvolvimento.
# Encerra ambos com Ctrl+C.
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$ROOT_DIR/api"
WEB_DIR="$ROOT_DIR/web"
VENV="$API_DIR/.venv"

pids=()

cleanup() {
  echo ""
  echo "Encerrando..."
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# --- API ---
if [ ! -d "$VENV" ]; then
  echo "venv da API não encontrado em $VENV" >&2
  echo "Crie com: cd api && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

echo "Iniciando API em http://localhost:8000 ..."
(
  cd "$API_DIR"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  exec uvicorn main:app --reload
) &
pids+=($!)

# --- Web ---
if [ ! -d "$WEB_DIR/node_modules" ]; then
  echo "Instalando dependências do web..."
  (cd "$WEB_DIR" && npm install)
fi

echo "Iniciando web em http://localhost:5173 ..."
(
  cd "$WEB_DIR"
  exec npm run dev
) &
pids+=($!)

echo ""
echo "API: http://localhost:8000  |  Web: http://localhost:5173  (Ctrl+C para parar)"
wait
