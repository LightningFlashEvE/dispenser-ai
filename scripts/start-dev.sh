#!/bin/bash
# ============================================================
# start-dev.sh — 启动测试/开发环境
#
# 启动服务：
#   1. whisper-server  :8081  ASR
#   2. llama-server    :8080  LLM
#   3. MeloTTS         :8020  TTS
#   4. mock-qt         :9000  C++ 控制程序模拟
#   5. backend         :8000  FastAPI 主服务
#   6. frontend        :5173  Vite 开发服务器
# ============================================================

set -u
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-runtime.sh"

echo ""
echo -e "${CYAN}=== dispenser-ai 测试环境启动 ===${RESET}"
echo ""

info "[1/6] whisper-server (ASR :8081)"
start_whisper_server || warn "whisper-server 启动失败（ASR 将不可用）"

info "[2/6] llama-server (LLM :8080)"
start_llama_server || { err "llama-server 启动失败，中止后续启动"; exit 1; }

info "[3/6] MeloTTS (TTS :8020)"
start_melotts

info "[4/6] mock-qt (C++ 控制程序模拟 :9000)"
start_mock_qt

info "[5/6] backend (FastAPI :8000)"
start_backend || err "backend 健康检查超时，请查看 logs/backend.log"

info "[6/6] frontend (Vite dev :5173)"
start_frontend_dev

echo ""
echo -e "${CYAN}=== 启动完成 ===${RESET}"
print_status

LAN_IP=$(get_lan_ip)
echo -e "${GREEN}开发前端 (本机):   ${FRONTEND_LOCAL_URL:-http://localhost:5173}${RESET}"
echo -e "${GREEN}开发前端 (局域网): ${FRONTEND_LAN_URL:-http://${LAN_IP}:5173}${RESET}"
echo -e "${YELLOW}提示: 局域网设备使用麦克风必须打开 HTTPS 地址；首次访问自签名证书页面时需要在浏览器中继续访问。${RESET}"
echo -e "${GREEN}后端 API:          http://${LAN_IP}:8000${RESET}"
