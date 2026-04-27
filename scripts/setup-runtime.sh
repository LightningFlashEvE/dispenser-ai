#!/usr/bin/env bash
set -euo pipefail

# Build/install external runtime components on Jetson Orin NX.
# This script restores directories that are intentionally not committed:
#   llama.cpp/     -> llama-server
#   whisper.cpp/   -> whisper-server
#   melotts-git/   -> MeloTTS + local HTTP wrapper

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CUDA_ARCH="${CUDA_ARCH:-87}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

LLAMA_CPP_REPO="${LLAMA_CPP_REPO:-https://github.com/ggml-org/llama.cpp.git}"
LLAMA_CPP_REF="${LLAMA_CPP_REF:-master}"
WHISPER_CPP_REPO="${WHISPER_CPP_REPO:-https://github.com/ggml-org/whisper.cpp.git}"
WHISPER_CPP_REF="${WHISPER_CPP_REF:-master}"
MELOTTS_REPO="${MELOTTS_REPO:-https://github.com/myshell-ai/MeloTTS.git}"
MELOTTS_REF="${MELOTTS_REF:-main}"

info() { echo "==> $*"; }
warn() { echo "WARN: $*" >&2; }

clone_if_missing() {
  local repo="$1" dir="$2" ref="$3"
  if [ -d "$dir/.git" ]; then
    info "$dir already exists"
    if [ "${UPDATE_EXTERNAL:-0}" = "1" ]; then
      git -C "$dir" fetch --depth 1 origin "$ref"
      git -C "$dir" checkout FETCH_HEAD
    fi
  elif [ -e "$dir" ]; then
    warn "$dir exists but is not a git checkout; skipping clone"
  else
    git clone --depth 1 --branch "$ref" "$repo" "$dir"
  fi
}

build_llama_cpp() {
  info "Building llama.cpp"
  clone_if_missing "$LLAMA_CPP_REPO" "$ROOT_DIR/llama.cpp" "$LLAMA_CPP_REF"
  cmake -S "$ROOT_DIR/llama.cpp" -B "$ROOT_DIR/llama.cpp/build" \
    -DGGML_CUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCH" \
    -DCMAKE_BUILD_TYPE=Release
  cmake --build "$ROOT_DIR/llama.cpp/build" --target llama-server -j"$(nproc)"
}

build_whisper_cpp() {
  info "Building whisper.cpp"
  clone_if_missing "$WHISPER_CPP_REPO" "$ROOT_DIR/whisper.cpp" "$WHISPER_CPP_REF"
  cmake -S "$ROOT_DIR/whisper.cpp" -B "$ROOT_DIR/whisper.cpp/build" \
    -DGGML_CUDA=ON \
    -DWHISPER_BUILD_TESTS=OFF \
    -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCH" \
    -DCMAKE_BUILD_TYPE=Release
  cmake --build "$ROOT_DIR/whisper.cpp/build" --target whisper-server -j"$(nproc)"
}

write_melotts_http_wrapper() {
  local target="$ROOT_DIR/melotts-git/melo/tts_server.py"
  if [ -f "$target" ] && [ "${OVERWRITE_MELOTTS_SERVER:-0}" != "1" ]; then
    info "MeloTTS HTTP wrapper already exists: $target"
    return
  fi

  info "Writing MeloTTS HTTP wrapper"
  cat > "$target" <<'PY'
from __future__ import annotations

import argparse
import base64
import tempfile
import wave
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from melo.api import TTS


class SpeakRequest(BaseModel):
    text: str
    interrupt: bool = False
    speed: float = 0.9


class SynthesizeRequest(BaseModel):
    text: str
    save: bool = True
    play: bool = False
    speed: float = 0.9


app = FastAPI(title="MeloTTS local service")
model: TTS | None = None
speaker_id: int | None = None


def get_model() -> TTS:
    global model, speaker_id
    if model is None:
        model = TTS(language="ZH")
        speakers = getattr(model.hps.data, "spk2id", None) or {}
        try:
            speaker_id = speakers["ZH"]
        except (TypeError, KeyError):
            speaker_id = list(speakers.values())[0] if speakers else 0
    return model


def render_wav(text: str, speed: float) -> dict:
    tts = get_model()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        output_path = Path(tmp.name)
    try:
        tts.tts_to_file(text, speaker_id, str(output_path), speed=speed)
        audio_bytes = output_path.read_bytes()
        sample_rate = 44100
        duration_ms = 0
        try:
            with wave.open(str(output_path), "rb") as wav:
                sample_rate = wav.getframerate()
                frames = wav.getnframes()
                duration_ms = int(frames / sample_rate * 1000)
        except wave.Error:
            pass
        return {
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "sample_rate": sample_rate,
            "format": "wav",
            "duration_ms": duration_ms,
        }
    finally:
        output_path.unlink(missing_ok=True)


@app.get("/health")
def health() -> dict:
    get_model()
    return {"status": "ok", "provider": "melotts"}


@app.post("/speak")
def speak(req: SpeakRequest) -> dict:
    return render_wav(req.text, req.speed)


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest) -> dict:
    return render_wav(req.text, req.speed)


@app.post("/stop")
def stop() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
PY
}

install_melotts() {
  info "Installing MeloTTS"
  clone_if_missing "$MELOTTS_REPO" "$ROOT_DIR/melotts-git" "$MELOTTS_REF"
  "$PYTHON_BIN" -m venv "$ROOT_DIR/melotts-git/venv"
  "$ROOT_DIR/melotts-git/venv/bin/python" -m pip install --upgrade pip wheel setuptools
  "$ROOT_DIR/melotts-git/venv/bin/pip" install -e "$ROOT_DIR/melotts-git"
  "$ROOT_DIR/melotts-git/venv/bin/pip" install "fastapi>=0.115" "uvicorn[standard]>=0.34"
  write_melotts_http_wrapper

  # Replace generic PyTorch (cu130) with Jetson CUDA 12.6 wheel
  local TORCH_URL="${TORCH_URL:-https://developer.download.nvidia.com/compute/redist/jp/v61/pytorch/torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl}"
  info "Replacing PyTorch with Jetson CUDA 12.6 wheel"
  "$ROOT_DIR/melotts-git/venv/bin/pip" uninstall torch torchaudio torchvision -y 2>/dev/null || true
  "$ROOT_DIR/melotts-git/venv/bin/pip" install --no-cache-dir "$TORCH_URL"

  # Patch torchaudio imports (not available on Jetson; MeloTTS falls back gracefully)
  local patched=0
  for f in api utils split_utils; do
    local src="$ROOT_DIR/melotts-git/melo/${f}.py"
    if [ -f "$src" ] && grep -q "^import torchaudio$" "$src" 2>/dev/null; then
      sed -i 's/^import torchaudio$/try:\n    import torchaudio\nexcept ImportError:\n    torchaudio = None/' "$src"
      patched=$((patched + 1))
    fi
  done
  info "Patched torchaudio imports in $patched files"

  "$ROOT_DIR/melotts-git/venv/bin/python" -c "from melo.api import TTS; TTS(language='ZH'); import torch; assert torch.cuda.is_available(), 'CUDA not available'" || {
    warn "MeloTTS CUDA init failed; TTS will use CPU"
  }
}

usage() {
  cat <<EOF
Usage: $0 [all|llama|whisper|melotts]

Environment:
  CUDA_ARCH=87                 Jetson Orin NX CUDA architecture
  UPDATE_EXTERNAL=1            Fetch and rebuild existing external repos
  OVERWRITE_MELOTTS_SERVER=1   Rewrite melotts-git/melo/tts_server.py
EOF
}

target="${1:-all}"
case "$target" in
  all)
    build_llama_cpp
    build_whisper_cpp
    install_melotts
    ;;
  llama) build_llama_cpp ;;
  whisper) build_whisper_cpp ;;
  melotts) install_melotts ;;
  -h|--help|help) usage ;;
  *) usage; exit 1 ;;
esac

info "Runtime setup complete"
