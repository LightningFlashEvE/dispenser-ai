#!/usr/bin/env bash
set -euo pipefail

# Jetson Orin NX / JetPack 6.x bootstrap script.
# Installs system packages and creates project venvs. It intentionally does
# not download large model files; run scripts/download-models.sh separately.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
NODE_MAJOR="${NODE_MAJOR:-20}"

info() { echo "==> $*"; }

configure_nginx() {
  local site_name="${NGINX_SITE_NAME:-dispenser-ai}"
  local ssl_dir="${NGINX_SSL_DIR:-/etc/nginx/ssl}"
  local cert_path="${NGINX_CERT_PATH:-${ssl_dir}/${site_name}.crt}"
  local key_path="${NGINX_KEY_PATH:-${ssl_dir}/${site_name}.key}"
  local site_available="/etc/nginx/sites-available/${site_name}"
  local site_enabled="/etc/nginx/sites-enabled/${site_name}"
  local lan_ip="${LAN_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"

  info "Configuring nginx production frontend"
  sudo mkdir -p "${ssl_dir}"

  if [ ! -s "${cert_path}" ] || [ ! -s "${key_path}" ]; then
    local cn="${lan_ip:-localhost}"
    local san="DNS:localhost,IP:127.0.0.1"
    if [ -n "${lan_ip}" ]; then
      san="IP:${lan_ip},${san}"
    fi
    sudo openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 825 \
      -keyout "${key_path}" -out "${cert_path}" \
      -subj "/CN=${cn}" -addext "subjectAltName=${san}" >/dev/null 2>&1
    info "Created nginx self-signed certificate: ${cert_path}"
  else
    info "Using existing nginx certificate: ${cert_path}"
  fi

  sed \
    -e "s#/path/to/cert.pem#${cert_path}#g" \
    -e "s#/path/to/cert.key#${key_path}#g" \
    -e "s#root /home/lightning/dispenser-ai/frontend/dist;#root ${ROOT_DIR}/frontend/dist;#g" \
    -e "s#alias /home/lightning/dispenser-ai/frontend/public/worklets/;#alias ${ROOT_DIR}/frontend/public/worklets/;#g" \
    "${ROOT_DIR}/scripts/nginx-ssl.conf" | sudo tee "${site_available}" >/dev/null

  sudo ln -sf "${site_available}" "${site_enabled}"
  sudo rm -f /etc/nginx/sites-enabled/default
  sudo nginx -t
  sudo systemctl enable --now nginx
  sudo systemctl reload nginx
}

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This setup script is intended for Ubuntu/JetPack systems with apt-get." >&2
  exit 1
fi

info "Installing system packages"
sudo apt-get update
sudo apt-get install -y \
  ca-certificates curl wget git git-lfs openssl \
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

info "Installing frontend dependencies"
npm --prefix "${ROOT_DIR}/frontend" install

configure_nginx

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
echo "  4. Start services with ./scripts/start-prod.sh"
