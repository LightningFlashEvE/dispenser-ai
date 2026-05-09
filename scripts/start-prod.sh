#!/bin/bash
# ============================================================
# start-prod.sh — 启动生产环境
#
# 启动服务：
#   1. whisper-server  :8081  ASR
#   2. llama-server    :8080  LLM
#   3. MeloTTS         :8020  TTS
#   4. backend         :8000  FastAPI 主服务
#   5. frontend dist          构建生产前端产物
#
# 生产环境不启动 mock-qt 和 Vite dev server。
# ============================================================

set -u
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-runtime.sh"

echo ""
echo -e "${CYAN}=== dispenser-ai 生产环境启动 ===${RESET}"
echo ""

info "[1/5] whisper-server (ASR :8081)"
start_whisper_server || warn "whisper-server 启动失败（ASR 将不可用）"

info "[2/5] llama-server (LLM :8080)"
start_llama_server || { err "llama-server 启动失败，中止后续启动"; exit 1; }

info "[3/5] MeloTTS (TTS :8020)"
start_melotts

info "[4/5] backend (FastAPI :8000)"
start_backend || err "backend 健康检查超时，请查看 logs/backend.log"

info "[5/5] frontend — 构建生产产物"
build_frontend_prod

echo ""
echo -e "${CYAN}=== 启动完成 ===${RESET}"
print_status

LAN_IP=$(get_lan_ip)
echo -e "${GREEN}前端入口 (nginx):  https://${LAN_IP}${RESET}"
echo -e "${GREEN}后端 API:          http://${LAN_IP}:8000${RESET}"
