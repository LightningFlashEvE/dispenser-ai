#!/bin/bash
# ============================================================
# start-all.sh — 按顺序启动所有服务
#
# 启动顺序（依赖排序）：
#   1. whisper-server  :8081  ASR
#   2. llama-server    :8080  LLM（GPU 加载约 30-60 秒）
#   3. MeloTTS         :8020  TTS
#   4. mock-qt         :9000  C++ 控制程序模拟（仅开发环境）
#   5. backend         :8000  FastAPI 主服务
#   6. mcp-server       stdio  MCP Server（AI 工具调用层）
#   7. frontend        :5173  Vue 前端（可选，生产环境用构建产物）
#
# 用法:
#   ./scripts/start-all.sh          # 启动全部（含 mock-qt 和 frontend）
#   ./scripts/start-all.sh --prod   # 生产模式（跳过 mock-qt 和 frontend）
# ============================================================

# 不用 set -e：每个服务独立容错，单个失败不中止整体启动序列
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${SCRIPT_DIR}"

# ── 颜色输出 ──────────────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
RESET="\033[0m"

ok()   { echo -e "${GREEN}  ✓ $1${RESET}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${RESET}"; }
err()  { echo -e "${RED}  ✗ $1${RESET}"; }
info() { echo -e "${CYAN}  → $1${RESET}"; }

# ── 参数解析 ──────────────────────────────────────────────────────
PROD_MODE=false
[[ "$1" == "--prod" ]] && PROD_MODE=true

# ── 代理绕过本地服务 ──────────────────────────────────────────────
export no_proxy="localhost,127.0.0.1,192.168.10.*"
export NO_PROXY="${no_proxy}"

# ── 等待端口就绪 ──────────────────────────────────────────────────
wait_for_url() {
    local url="$1" name="$2" timeout="${3:-60}"
    info "等待 ${name} 就绪 (最多 ${timeout}s)..."
    for i in $(seq 1 "${timeout}"); do
        if curl -ksf "${url}" >/dev/null 2>&1; then
            ok "${name} 已就绪"
            return 0
        fi
        sleep 1
    done
    err "${name} 启动超时，请检查日志"
    return 1
}

# ── 端口监听检测（比 kill -0 可靠，避免 PID 被回收误判）────────────
is_port_listening() {
    local port="$1"
    # 优先用 ss，回退到 netstat
    if command -v ss &>/dev/null; then
        ss -tlnp 2>/dev/null | grep -q ":${port} "
    else
        netstat -tlnp 2>/dev/null | grep -q ":${port} "
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
    pids="$(port_pids "${port}")" || return 1
    [ -z "${pids}" ] && return 1
    warn "${label} 已被旧进程占用，正在释放 :${port} -> ${pids}"
    kill ${pids} 2>/dev/null || true
    sleep 1
    return 0
}

get_lan_ip() {
    hostname -I 2>/dev/null | awk '{print $1}'
}

ensure_frontend_dev_cert() {
    local lan_ip="$1"
    local cert_dir="${SCRIPT_DIR}/.certs"
    local cert_path="${cert_dir}/vite-dev.crt"
    local key_path="${cert_dir}/vite-dev.key"
    local cn="${lan_ip:-localhost}"
    local san="DNS:localhost,IP:127.0.0.1"

    if [ -n "${lan_ip}" ]; then
        san="IP:${lan_ip},${san}"
    fi

    if [ -s "${cert_path}" ] && [ -s "${key_path}" ]; then
        echo "${cert_path}|${key_path}"
        return 0
    fi

    if ! command -v openssl &>/dev/null; then
        warn "未找到 openssl，开发前端将以 HTTP 启动；局域网访问时浏览器会禁用麦克风" >&2
        return 1
    fi

    mkdir -p "${cert_dir}"
    if openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 825 \
        -keyout "${key_path}" -out "${cert_path}" \
        -subj "/CN=${cn}" -addext "subjectAltName=${san}" >/dev/null 2>&1; then
        echo "${cert_path}|${key_path}"
        return 0
    fi

    warn "生成 Vite 开发 HTTPS 证书失败，开发前端将以 HTTP 启动；局域网访问时浏览器会禁用麦克风" >&2
    return 1
}

frontend_scheme_matches() {
    local expected_url="$1"
    curl -ksf "${expected_url}" >/dev/null 2>&1
}

echo ""
echo -e "${CYAN}=== dispenser-ai 启动序列 ===${RESET}"
echo ""

# ── 1. whisper-server ─────────────────────────────────────────────
info "[1/6] whisper-server (ASR :8081)"
bash scripts/start-whisper-server.sh start || warn "whisper-server 启动失败（ASR 将不可用）"
wait_for_url "http://127.0.0.1:8081/" "whisper-server" 15 || true

# ── 2. llama-server ───────────────────────────────────────────────
info "[2/6] llama-server (LLM :8080)"
bash llama_server.sh start || { err "llama-server 启动失败，中止后续启动"; exit 1; }
# Jetson GPU 加载 Qwen3-4B 约 30-60s，给足 120s
wait_for_url "http://127.0.0.1:8080/health" "llama-server" 120 || { err "LLM 服务无响应，请检查 logs/llama_server.log"; exit 1; }

# ── 3. MeloTTS ────────────────────────────────────────────────────
info "[3/6] MeloTTS (TTS :8020)"
mkdir -p logs
PID_FILE=".melotts.pid"
if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    ok "MeloTTS 已在运行 (PID: $(cat "${PID_FILE}"))"
else
    MELOTTS_PY=""
    for candidate in \
        "${SCRIPT_DIR}/melotts-git/venv/bin/python" \
        "$(which python3 2>/dev/null)" \
        "$(which python 2>/dev/null)"; do
        if [ -x "${candidate}" ]; then MELOTTS_PY="${candidate}"; break; fi
    done

    if [ -z "${MELOTTS_PY}" ]; then
        warn "未找到 Python，MeloTTS 跳过（TTS 将降级静默）"
    else
        nohup "${MELOTTS_PY}" "${SCRIPT_DIR}/melotts-git/melo/tts_server.py" --port 8020 \
            >> "${SCRIPT_DIR}/logs/melotts.log" 2>&1 &
        melotts_pid=$!
        echo "${melotts_pid}" > "${PID_FILE}"
        ok "MeloTTS 已启动 (PID: ${melotts_pid})"
        # 首次运行会下载模型，可能超过 30s；warn 而不 exit
        wait_for_url "http://127.0.0.1:8020/health" "MeloTTS" 60 || warn "MeloTTS 未响应（首次运行可能正在下载模型，TTS 暂时不可用）"
    fi
fi

# ── 4. mock-qt（开发环境）────────────────────────────────────────
if [ "${PROD_MODE}" = false ]; then
    info "[4/6] mock-qt (C++ 控制程序模拟 :9000)"
    PID_FILE_MQ=".mock_qt.pid"
    if [ -f "${PID_FILE_MQ}" ] && kill -0 "$(cat "${PID_FILE_MQ}")" 2>/dev/null; then
        ok "mock-qt 已在运行 (PID: $(cat "${PID_FILE_MQ}"))"
    else
        MOCK_PY="mock-qt/venv/bin/python"
        if [ ! -x "${MOCK_PY}" ]; then MOCK_PY="$(which python3 2>/dev/null)"; fi
        if [ -f "${SCRIPT_DIR}/mock-qt/server.py" ] && [ -n "${MOCK_PY}" ]; then
            nohup "${MOCK_PY}" "${SCRIPT_DIR}/mock-qt/server.py" --port 9000 \
                >> "${SCRIPT_DIR}/logs/mock_qt.log" 2>&1 &
            mock_pid=$!
            echo "${mock_pid}" > "${PID_FILE_MQ}"
            ok "mock-qt 已启动 (PID: ${mock_pid})"
            wait_for_url "http://127.0.0.1:9000/api/status" "mock-qt" 10 || warn "mock-qt 未响应"
        else
            warn "mock-qt 跳过（文件或 Python 不可用）"
        fi
    fi
else
    info "[4/6] mock-qt — 生产模式，已跳过"
fi

# ── 5. backend ────────────────────────────────────────────────────
info "[5/7] backend (FastAPI :8000)"
PID_FILE_BE=".backend.pid"
if is_port_listening 8000 && curl -ksf "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
    ok "backend 已在监听 :8000（运行中）"
elif [ -f "${PID_FILE_BE}" ] && kill -0 "$(cat "${PID_FILE_BE}")" 2>/dev/null; then
    ok "backend 已在运行 (PID: $(cat "${PID_FILE_BE}"))"
else
    BACKEND_UVICORN="${SCRIPT_DIR}/backend/venv/bin/uvicorn"
    if [ ! -x "${BACKEND_UVICORN}" ]; then
        err "backend venv 不存在，请先运行: ./scripts/setup-nx.sh"
        err "无法启动 backend，后续服务跳过"
    else
        # 切换到 backend/ 目录，用 setsid 隔离 session 防止信号干扰
        mkdir -p "${SCRIPT_DIR}/logs"
        (
            cd "${SCRIPT_DIR}/backend" || exit 1
            setsid "${BACKEND_UVICORN}" app.main:app \
                --host 0.0.0.0 --port 8000 --workers 1 \
                >> "${SCRIPT_DIR}/logs/backend.log" 2>&1 &
            echo $!
        ) > "${PID_FILE_BE}"
        BACKEND_PID=$(cat "${PID_FILE_BE}")
        ok "backend 已启动 (PID: ${BACKEND_PID})"
        wait_for_url "http://127.0.0.1:8000/health" "backend" 20 || err "backend 健康检查超时，请查看 logs/backend.log"
    fi
fi

# ── 6. mcp-server ─────────────────────────────────────────────────
info "[6/7] mcp-server (stdio 模式)"
PID_FILE_MCP=".mcp_server.pid"
if [ -f "${PID_FILE_MCP}" ] && kill -0 "$(cat "${PID_FILE_MCP}")" 2>/dev/null; then
    ok "mcp-server 已在运行 (PID: $(cat "${PID_FILE_MCP}"))"
else
    MCP_PY="${SCRIPT_DIR}/mcp-server/venv/bin/python"
    if [ ! -x "${MCP_PY}" ]; then
        # 尝试创建 venv 并安装依赖
        if [ -d "${SCRIPT_DIR}/mcp-server" ] && [ -f "${SCRIPT_DIR}/mcp-server/requirements.txt" ]; then
            info "mcp-server venv 不存在，正在创建..."
            python3 -m venv "${SCRIPT_DIR}/mcp-server/venv" 2>/dev/null || warn "创建 mcp-server venv 失败"
            if [ -x "${SCRIPT_DIR}/mcp-server/venv/bin/pip" ]; then
                "${SCRIPT_DIR}/mcp-server/venv/bin/pip" install -q -r "${SCRIPT_DIR}/mcp-server/requirements.txt" 2>/dev/null || warn "安装 mcp-server 依赖失败"
                MCP_PY="${SCRIPT_DIR}/mcp-server/venv/bin/python"
            fi
        fi
    fi

    if [ -x "${MCP_PY}" ] && [ -f "${SCRIPT_DIR}/mcp-server/server.py" ]; then
        mkdir -p logs
        nohup "${MCP_PY}" "${SCRIPT_DIR}/mcp-server/server.py" \
            >> "${SCRIPT_DIR}/logs/mcp_server.log" 2>&1 &
        mcp_pid=$!
        echo "${mcp_pid}" > "${PID_FILE_MCP}"
        ok "mcp-server 已启动 (PID: ${mcp_pid})"
    else
        warn "mcp-server 跳过（venv 或 server.py 不可用）"
    fi
fi

# ── 7. frontend ──────────────────────────────────────────────────
if [ "${PROD_MODE}" = false ]; then
    info "[7/7] frontend (Vite dev :5173)"
    PID_FILE_FE=".frontend.pid"
    LAN_IP=$(get_lan_ip)
    FRONTEND_LOCAL_URL="http://localhost:5173"
    FRONTEND_LAN_URL="http://${LAN_IP}:5173"
    FRONTEND_WAIT_URL="http://127.0.0.1:5173"
    FRONTEND_ENV=""

    cert_pair="$(ensure_frontend_dev_cert "${LAN_IP}")"
    if [ $? -eq 0 ]; then
        cert_path="${cert_pair%%|*}"
        key_path="${cert_pair##*|}"
        FRONTEND_LOCAL_URL="https://localhost:5173"
        FRONTEND_LAN_URL="https://${LAN_IP}:5173"
        FRONTEND_WAIT_URL="https://127.0.0.1:5173"
        FRONTEND_ENV="USE_HTTPS=true SSL_CERT_PATH='${cert_path}' SSL_KEY_PATH='${key_path}'"
    fi

    if is_port_listening 5173; then
        if frontend_scheme_matches "${FRONTEND_WAIT_URL}"; then
            ok "frontend 已在监听 :5173（Vite 运行中）"
        else
            warn "frontend 已监听 :5173，但当前协议与预期不一致"
            if ! stop_port_processes 5173 "frontend"; then
                warn "无法自动释放 :5173，请先停止旧的 Vite 进程后再重试"
            fi
        fi
    fi

    if is_port_listening 5173; then
        if frontend_scheme_matches "${FRONTEND_WAIT_URL}"; then
            :
        else
            warn "frontend 端口仍被占用，跳过重新启动"
        fi
    elif [ -d "${SCRIPT_DIR}/frontend/node_modules" ]; then
        # 清理可能残留的旧 PID 文件（PID 已被系统回收）
        rm -f "${PID_FILE_FE}"
        # 必须 cd 到 frontend/ 目录，否则 Vite 找不到 vite.config.ts
        nohup bash -c "cd '${SCRIPT_DIR}/frontend' && ${FRONTEND_ENV} exec npx vite --host 0.0.0.0 --port 5173" \
            >> "${SCRIPT_DIR}/logs/frontend.log" 2>&1 &
        echo $! > "${PID_FILE_FE}"
        ok "frontend 已启动 (PID: $!)"
        wait_for_url "${FRONTEND_WAIT_URL}" "frontend" 25 || warn "frontend 未响应（Vite 首次启动较慢，可稍后访问）"
    else
        warn "frontend/node_modules 不存在，请先运行: cd frontend && npm install"
    fi
else
    info "[7/7] frontend — 生产模式，执行 vite build 重建产物..."
    if [ ! -d "${SCRIPT_DIR}/frontend/node_modules" ]; then
        warn "frontend/node_modules 不存在，请先运行: cd frontend && npm install"
        warn "跳过构建，nginx 将继续使用旧的 dist/"
    else
        (
            cd "${SCRIPT_DIR}/frontend" || exit 1
            npx vite build >> "${SCRIPT_DIR}/logs/frontend_build.log" 2>&1
        )
        if [ $? -eq 0 ]; then
            ok "frontend 构建完成 → frontend/dist/"
            # 如果 nginx 正在运行，自动重载使其服务最新 dist
            if command -v nginx &>/dev/null && pgrep -x nginx &>/dev/null; then
                nginx -s reload 2>/dev/null && ok "nginx 已重载，新前端已生效" || warn "nginx reload 失败，请手动执行: sudo nginx -s reload"
            else
                info "nginx 未运行，dist 已就绪，nginx 启动后将自动使用新版本"
            fi
        else
            err "frontend 构建失败，请检查 logs/frontend_build.log"
        fi
    fi
fi

# ── 汇总 ─────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}=== 启动完成 ===${RESET}"
bash scripts/status.sh
echo ""
if [ "${PROD_MODE}" = true ]; then
    LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    echo -e "${GREEN}前端入口 (nginx):  https://${LAN_IP}${RESET}"
    echo -e "${GREEN}后端 API:          http://${LAN_IP}:8000${RESET}"
else
    LAN_IP=$(get_lan_ip)
    echo -e "${GREEN}开发前端 (本机):   ${FRONTEND_LOCAL_URL:-http://localhost:5173}${RESET}"
    echo -e "${GREEN}开发前端 (局域网): ${FRONTEND_LAN_URL:-http://${LAN_IP}:5173}${RESET}"
    echo -e "${YELLOW}提示: 局域网设备使用麦克风必须打开 HTTPS 地址；首次访问自签名证书页面时需要在浏览器中继续访问。${RESET}"
    echo -e "${GREEN}后端 API:          http://${LAN_IP}:8000${RESET}"
fi
