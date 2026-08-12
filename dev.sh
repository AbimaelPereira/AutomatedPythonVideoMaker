#!/usr/bin/env bash
#
# Sobe a API (FastAPI/uvicorn) e o frontend web (Vite) juntos para desenvolvimento.
# Encerra ambos com Ctrl+C.
#
# Opcional:
#   NO_WEB=1 ./dev.sh    → sobe só a API (útil ao rodar o videomaker, que precisa
#                          da API para resolver remote assets, mas não do front)
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$ROOT_DIR/api"
WEB_DIR="$ROOT_DIR/web"
VENV="$API_DIR/.venv"

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

pids=()

cleanup() {
  echo ""
  echo "Encerrando..."
  for pid in "${pids[@]:-}"; do
    # Pula entrada vazia (acontece quando o script sai antes de subir algo).
    [ -n "$pid" ] || continue
    # `-$pid` mata o process group inteiro. Necessário porque
    # `uvicorn --reload` e `npm run dev` (que executa `vite`) criam processos
    # filhos: matar só o PID pai deixava órfãos segurando as portas, e o
    # ./dev.sh seguinte falhava com "address already in use".
    kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

port_busy() {
  # Sem depender de lsof/ss: tenta abrir a porta via /dev/tcp.
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && exec 3>&- && return 0
  return 1
}

# --- Pré-checagens -----------------------------------------------------------

if [ ! -d "$VENV" ]; then
  echo "venv da API não encontrado em $VENV" >&2
  echo "Crie com: cd api && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

if [ ! -f "$API_DIR/.env" ]; then
  echo "AVISO: $API_DIR/.env não encontrado — a API vai usar defaults (MySQL provavelmente falha)." >&2
fi

for port in "$API_PORT" "$WEB_PORT"; do
  if port_busy "$port"; then
    echo "Porta $port já está em uso. Encerre o processo antes de subir o dev." >&2
    echo "  Quem está usando: (ss -ltnp | grep :$port)  ou  (lsof -i :$port)" >&2
    exit 1
  fi
done

# SERVICE_TOKEN autentica as chamadas internas do videomaker → API
# (X-Service-Token em /remote-assets/internal/*). Se os dois lados não tiverem o
# MESMO valor, a API responde "Service token inválido" e o videomaker não resolve
# nenhum remote_asset — falhando de um jeito que parece problema de rede.
read_env_var() {
  # $1 = arquivo .env, $2 = chave. Vazio se o arquivo/chave não existir.
  # O `|| true` é essencial: sem ele, um grep sem match (exit 1) derruba o
  # script por causa do `set -e`.
  [ -f "$1" ] || return 0
  grep -sE "^[[:space:]]*$2=" "$1" 2>/dev/null | tail -1 | cut -d= -f2- \
    | tr -d '"'"'"' \r' || true
}

api_token="$(read_env_var "$API_DIR/.env" SERVICE_TOKEN)"
vm_token="$(read_env_var "$ROOT_DIR/videomaker/.env" SERVICE_TOKEN)"

if [ -n "$vm_token" ] && [ "$api_token" != "$vm_token" ]; then
  if [ -z "$api_token" ]; then
    echo "AVISO: videomaker/.env define SERVICE_TOKEN, mas api/.env não." >&2
  else
    echo "AVISO: SERVICE_TOKEN difere entre api/.env e videomaker/.env." >&2
  fi
  echo "        Chamadas do videomaker à API (remote assets) seriam recusadas." >&2
  echo "        Subindo a API com o token do videomaker só nesta execução." >&2
  echo "        Para resolver de vez, use o mesmo SERVICE_TOKEN nos dois .env." >&2
  export SERVICE_TOKEN="$vm_token"
fi

# --- API ---------------------------------------------------------------------

echo "Iniciando API em http://localhost:$API_PORT ..."
setsid bash -c '
  cd "$1" || exit 1
  # shellcheck disable=SC1091
  source "$2/bin/activate"
  exec uvicorn main:app --reload --port "$3"
' _ "$API_DIR" "$VENV" "$API_PORT" &
pids+=($!)

# --- Web ---------------------------------------------------------------------

if [ "${NO_WEB:-0}" != "1" ]; then
  if [ ! -d "$WEB_DIR/node_modules" ]; then
    echo "Instalando dependências do web..."
    (cd "$WEB_DIR" && npm install)
  fi

  echo "Iniciando web em http://localhost:$WEB_PORT ..."
  setsid bash -c '
    cd "$1" || exit 1
    exec npm run dev -- --port "$2"
  ' _ "$WEB_DIR" "$WEB_PORT" &
  pids+=($!)
fi

echo ""
if [ "${NO_WEB:-0}" = "1" ]; then
  echo "API: http://localhost:$API_PORT  (NO_WEB=1, front não subiu)  (Ctrl+C para parar)"
else
  echo "API: http://localhost:$API_PORT  |  Web: http://localhost:$WEB_PORT  (Ctrl+C para parar)"
fi
wait
