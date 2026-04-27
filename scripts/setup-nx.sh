#!/usr/bin/env bash
set -euo pipefail

# Jetson Orin NX / JetPack 6.x bootstrap script.
# Installs system packages and creates project venvs. It intentionally does
# not download large model files; run scripts/download-models.sh separately.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
NODE_MAJOR="${NODE_MAJOR:-20}"

info() { echo "==> $*"; }

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This setup script is intended for Ubuntu/JetPack systems with apt-get." >&2
  exit 1
fi

info "Installing system packages"
sudo apt-get update
sudo apt-get install -y \
  ca-certificates curl wget git git-lfs \
  build-essential cmake ninja-build pkg-config \
  "${PYTHON_BIN}" python3-venv python3-dev python3-pip \
  sqlite3 ffmpeg v4l-utils alsa-utils portaudio19-dev \
  libopencv-dev libopenblas-dev libsndfile1 \
  nginx net-tools

if ! command -v node >/dev/null 2>&1 || ! node -e "process.exit(Number(process.versions.node.split('.')[0]) >= ${NODE_MAJOR} ? 0 : 1)" >/dev/null 2>&1; then
  info "Installing Node.js ${NODE_MAJOR}.x from NodeSource"
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | sudo -E bash -
  sudo apt-get install -y nodejs
fi

info "Creating backend venv"
"${PYTHON_BIN}" -m venv "${ROOT_DIR}/backend/venv"
"${ROOT_DIR}/backend/venv/bin/python" -m pip install --upgrade pip wheel setuptools
"${ROOT_DIR}/backend/venv/bin/pip" install -r "${ROOT_DIR}/backend/requirements.txt"

info "Creating mcp-server venv"
"${PYTHON_BIN}" -m venv "${ROOT_DIR}/mcp-server/venv"
"${ROOT_DIR}/mcp-server/venv/bin/python" -m pip install --upgrade pip wheel setuptools
"${ROOT_DIR}/mcp-server/venv/bin/pip" install -r "${ROOT_DIR}/mcp-server/requirements.txt"

info "Installing frontend dependencies"
npm --prefix "${ROOT_DIR}/frontend" install

if [ ! -f "${ROOT_DIR}/backend/.env" ]; then
  cp "${ROOT_DIR}/backend/.env.example" "${ROOT_DIR}/backend/.env"
  info "Created backend/.env from backend/.env.example"
fi

mkdir -p "${ROOT_DIR}/logs" "${ROOT_DIR}/models/Qwen" "${ROOT_DIR}/models/whisper"

info "Bootstrap complete"
echo "Next steps:"
echo "  1. Edit backend/.env for your hardware ports and model paths."
echo "  2. Run scripts/download-models.sh after setting QWEN_GGUF_URL."
echo "  3. Run scripts/setup-runtime.sh to build llama.cpp/whisper.cpp and install MeloTTS."
echo "  4. Start services with ./scripts/start-all.sh --prod"
