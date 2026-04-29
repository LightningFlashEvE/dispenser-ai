#!/bin/bash
# ============================================================
# status.sh — 检查所有服务运行状态
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${SCRIPT_DIR}"

GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; CYAN="\033[0;36m"; RESET="\033[0m"

check_service() {
    local name="$1" pid_file="$2" health_url="$3"
    local pid_status="停止" health_status=""

    if [ -f "${pid_file}" ]; then
        local pid=$(cat "${pid_file}")
        if kill -0 "${pid}" 2>/dev/null; then
            pid_status="运行中 (PID: ${pid})"
        else
            pid_status="PID 文件残留（进程已退出）"
        fi
    fi

    if [ -n "${health_url}" ]; then
        if curl -ksf "${health_url}" >/dev/null 2>&1; then
            health_status="${GREEN}健康${RESET}"
        else
            health_status="${RED}无响应${RESET}"
        fi
    fi

    local pid_color
    if echo "${pid_status}" | grep -q "运行中"; then
        pid_color="${GREEN}"
    elif echo "${pid_status}" | grep -q "停止"; then
        pid_color="${YELLOW}"
    else
        pid_color="${RED}"
    fi

    printf "  %-18s  ${pid_color}%-40s${RESET}" "${name}" "${pid_status}"
    [ -n "${health_status}" ] && printf "  %b" "${health_status}"
    echo ""
}

check_frontend() {
    local health_url="https://127.0.0.1:5173"
    if ! curl -ksf "${health_url}" >/dev/null 2>&1; then
        health_url="http://127.0.0.1:5173"
    fi
    check_service "frontend" ".frontend.pid" "${health_url}"
}

echo ""
echo -e "${CYAN}=== 服务状态 ===${RESET}"
echo ""
printf "  %-18s  %-40s  %s\n" "服务" "进程状态" "健康检查"
printf "  %s\n" "------------------------------------------------------------------------"

check_service "whisper-server" ".whisper_server.pid" "http://127.0.0.1:8081/"
check_service "llama-server"   ".llama_server.pid"   "http://127.0.0.1:8080/health"
check_service "MeloTTS"        ".melotts.pid"         "http://127.0.0.1:8020/health"
check_service "mock-qt"        ".mock_qt.pid"         "http://127.0.0.1:9000/api/status"
check_service "backend"        ".backend.pid"         "http://127.0.0.1:8000/health"
check_service "mcp-server"     ".mcp_server.pid"      ""
check_frontend

echo ""
echo -e "${CYAN}日志目录: ${SCRIPT_DIR}/logs/${RESET}"
if [ -d "logs" ]; then
    for f in logs/*.log; do
        [ -f "${f}" ] && printf "  %-30s  %s\n" "$(basename "${f}")" "$(wc -l < "${f}") 行"
    done
fi
echo ""
