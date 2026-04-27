#!/bin/bash
# ============================================================
# stop-all.sh — 停止所有服务
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${SCRIPT_DIR}"

GREEN="\033[0;32m"; YELLOW="\033[1;33m"; CYAN="\033[0;36m"; RESET="\033[0m"
ok()   { echo -e "${GREEN}  ✓ $1${RESET}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${RESET}"; }
info() { echo -e "${CYAN}  → $1${RESET}"; }

stop_pid_file() {
    local name="$1" pid_file="$2"
    if [ -f "${pid_file}" ]; then
        local pid=$(cat "${pid_file}")
        if kill -0 "${pid}" 2>/dev/null; then
            info "停止 ${name} (PID: ${pid})..."
            kill "${pid}" 2>/dev/null
            for i in $(seq 1 8); do
                kill -0 "${pid}" 2>/dev/null || { rm -f "${pid_file}"; ok "${name} 已停止"; return; }
                sleep 1
            done
            kill -9 "${pid}" 2>/dev/null
            rm -f "${pid_file}"
            ok "${name} 已强制停止"
        else
            warn "${name} 未在运行（PID 文件残留）"
            rm -f "${pid_file}"
        fi
    else
        warn "${name} 未在运行"
    fi
}

echo ""
echo -e "${CYAN}=== 停止所有服务 ===${RESET}"
echo ""

# 按启动顺序逆序停止
stop_pid_file "frontend"      ".frontend.pid"
stop_pid_file "mcp-server"    ".mcp_server.pid"
stop_pid_file "backend"       ".backend.pid"
stop_pid_file "mock-qt"       ".mock_qt.pid"
stop_pid_file "MeloTTS"       ".melotts.pid"
bash llama_server.sh stop
bash scripts/start-whisper-server.sh stop

echo ""
ok "所有服务已停止"
