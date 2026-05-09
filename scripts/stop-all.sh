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

port_pids() {
    local port="$1"
    if command -v fuser &>/dev/null; then
        fuser "${port}/tcp" 2>/dev/null | xargs -r echo
        return 0
    fi
    if command -v lsof &>/dev/null; then
        lsof -ti tcp:"${port}" 2>/dev/null
        return 0
    fi
    return 1
}

stop_port_processes() {
    local port="$1" label="$2"
    local pids
    pids="$(port_pids "${port}")" || return 0
    [ -z "${pids}" ] && return 0

    warn "${label} 端口 :${port} 仍被占用，正在停止 PID: ${pids}"
    kill ${pids} 2>/dev/null || true
    for i in $(seq 1 5); do
        sleep 1
        pids="$(port_pids "${port}")" || return 0
        [ -z "${pids}" ] && { ok "${label} :${port} 已释放"; return 0; }
    done
    kill -9 ${pids} 2>/dev/null || true
    ok "${label} :${port} 已强制释放"
}

echo ""
echo -e "${CYAN}=== 停止所有服务 ===${RESET}"
echo ""

# 按启动顺序逆序停止
stop_pid_file "frontend"      ".frontend.pid"
stop_port_processes 5173 "frontend/Vite"
stop_port_processes 5174 "frontend/Vite preview"
stop_pid_file "mcp-server"    ".mcp_server.pid"
stop_pid_file "backend"       ".backend.pid"
stop_pid_file "mock-qt"       ".mock_qt.pid"
stop_pid_file "MeloTTS"       ".melotts.pid"
bash llama_server.sh stop
bash scripts/start-whisper-server.sh stop

echo ""
ok "所有服务已停止"
