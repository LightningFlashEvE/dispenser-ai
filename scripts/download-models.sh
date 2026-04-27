#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QWEN_DIR="$ROOT_DIR/models/Qwen"
WHISPER_DIR="$ROOT_DIR/models/whisper"

mkdir -p "$QWEN_DIR" "$WHISPER_DIR"

download_file() {
  local url="$1"
  local output="$2"

  if [[ -f "$output" ]]; then
    echo "Already exists: $output"
    return
  fi

  if [[ -z "$url" || "$url" == "TODO" ]]; then
    echo "Missing URL for $output"
    echo "Set the matching environment variable or edit this script."
    return 0
  fi

  echo "Downloading $url"
  curl -L --fail --progress-bar "$url" -o "$output"
}

# Stable Hugging Face "resolve" URL. Hugging Face may redirect this to a
# short-lived cas-bridge.xethub signed URL; do not commit those signed URLs.
QWEN_GGUF_URL="${QWEN_GGUF_URL:-https://huggingface.co/Edge-Quant/Qwen3-4B-Instruct-2507-Q4_K_M-GGUF/resolve/main/qwen3-4b-instruct-2507-q4_k_m.gguf}"

WHISPER_BASE_URL="${WHISPER_BASE_URL:-https://huggingface.co/ggml-org/whisper.cpp/resolve/main/ggml-base.bin}"
WHISPER_SMALL_URL="${WHISPER_SMALL_URL:-https://huggingface.co/ggml-org/whisper.cpp/resolve/main/ggml-small.bin}"

download_file "$QWEN_GGUF_URL" "$QWEN_DIR/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
download_file "$WHISPER_BASE_URL" "$WHISPER_DIR/ggml-base.bin"

if [[ "${DOWNLOAD_WHISPER_SMALL:-0}" == "1" ]]; then
  download_file "$WHISPER_SMALL_URL" "$WHISPER_DIR/ggml-small.bin"
fi

echo "Model download step finished."
echo "If Qwen download was skipped, set QWEN_GGUF_URL and run again."
