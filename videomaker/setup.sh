#!/usr/bin/env bash
# setup.sh — configura o ambiente do AutomatedPythonVideoMaker do zero
# Testado em Ubuntu 22.04 LTS, Python 3.10
set -euo pipefail

PYTHON=python3.10

echo "=== AutomatedPythonVideoMaker — Setup ==="
echo ""

# ── 1. Dependências do sistema ────────────────────────────────────────────────
echo "[1/5] Instalando dependências do sistema..."
sudo apt-get update -qq
sudo apt-get install -y \
  python3.10 python3.10-venv python3-pip \
  ffmpeg \
  imagemagick \
  libsndfile1

# MoviePy usa TextClip via ImageMagick. A política padrão do Ubuntu bloqueia
# operações de render; essa correção é necessária para legendas funcionarem.
POLICY=/etc/ImageMagick-6/policy.xml
if [ -f "$POLICY" ] && grep -q 'rights="none" pattern="@\*"' "$POLICY"; then
  echo "   Ajustando policy.xml do ImageMagick para permitir TextClip..."
  sudo sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/' "$POLICY"
fi

echo "   OK."
echo ""

# ── 2. PyTorch ────────────────────────────────────────────────────────────────
# torch não está no requirements.txt porque o índice de instalação varia
# conforme a versão de CUDA disponível na máquina.
echo "[2/5] Instalando PyTorch 2.1.1..."
if command -v nvidia-smi &>/dev/null; then
  CUDA_VER=$(nvidia-smi 2>/dev/null | grep -oP "CUDA Version: \K[\d.]+" || echo "")
  echo "   GPU NVIDIA detectada. CUDA: ${CUDA_VER:-desconhecida}"
  if [[ "${CUDA_VER}" == 12.* ]]; then
    $PYTHON -m pip install torch==2.1.1 --index-url https://download.pytorch.org/whl/cu121
  elif [[ "${CUDA_VER}" == 11.8* ]] || [[ "${CUDA_VER}" == 11.7* ]]; then
    $PYTHON -m pip install torch==2.1.1 --index-url https://download.pytorch.org/whl/cu118
  else
    echo "   CUDA ${CUDA_VER} sem mapeamento definido — usando build CPU."
    $PYTHON -m pip install torch==2.1.1 --index-url https://download.pytorch.org/whl/cpu
  fi
else
  echo "   Sem GPU detectada — instalando PyTorch CPU."
  $PYTHON -m pip install torch==2.1.1 --index-url https://download.pytorch.org/whl/cpu
fi
echo "   OK."
echo ""

# ── 3. Dependências Python ────────────────────────────────────────────────────
echo "[3/5] Instalando requirements.txt..."
$PYTHON -m pip install --upgrade pip
$PYTHON -m pip install -r requirements.txt
echo "   OK."
echo ""

# ── 4. Estrutura de diretórios ────────────────────────────────────────────────
echo "[4/5] Criando diretórios necessários..."
mkdir -p output temp cache tokens assets/audio assets/fonts assets/image assets/video
echo "   OK."
echo ""

# ── 5. Arquivo .env ───────────────────────────────────────────────────────────
echo "[5/5] Configurando .env..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "   .env criado a partir do .env.example."
  echo "   IMPORTANTE: preencha o .env com suas chaves antes de executar."
else
  echo "   .env já existe — mantido sem alterações."
fi
echo ""

echo "=== Setup concluído! ==="
echo ""
echo "Próximos passos:"
echo ""
echo "  1. Preencha o .env com suas chaves de API (GEMINI_API_KEY, etc.)"
echo ""
echo "  2. Coloque os arquivos de credenciais em tokens/:"
echo "       tokens/youtube_client_secret.json     <- YouTube (OAuth)"
echo "       tokens/tts-automate-videos-XXXX.json  <- Google Cloud TTS (service account)"
echo "       tokens/<canal>.json                   <- gerado automaticamente no 1º upload"
echo ""
echo "  3. Execute:"
echo "       python main.py jsons/seu_arquivo.json"
echo "       DEBUG=1 python main.py jsons/seu_arquivo.json  # sem upload"
echo ""
