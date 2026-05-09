#!/bin/bash
# Shared runtime helpers for dispenser-ai start/stop scripts.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${SCRIPT_DIR}" || exit 1

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
RESET="\033[0m"

ok()   { echo -e "${GREEN}  ✓ $1${RESET}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${RESET}"; }
err()  { echo -e "${RED}  ✗ $1${RESET}"; }
info() { echo -e "${CYAN}  → $1${RESET}"; }

export no_proxy="localhost,127.0.0.1,192.168.10.*"
export NO_PROXY="${no_proxy}"

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

is_port_listening() {
    local port="$1"
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

load_whisper_env() {
    local env_file="${SCRIPT_DIR}/backend/.env"
    if [ -f "${env_file}" ]; then
        export $(grep -E '^(WHISPER_SERVER_URL|WHISPER_CPP_MODEL_PATH|WHISPER_LANGUAGE|AUDIO_SAMPLE_RATE)=' "${env_file}" | xargs 2>/dev/null)
    fi
    WHISPER_PORT="${WHISPER_PORT:-8081}"
    WHISPER_MODEL_PATH="${WHISPER_CPP_MODEL_PATH:-${SCRIPT_DIR}/models/whisper/ggml-base.bin}"
    WHISPER_LANGUAGE="${WHISPER_LANGUAGE:-zh}"
    WHISPER_PID_FILE="${SCRIPT_DIR}/.whisper_server.pid"
    WHISPER_LOG_FILE="${SCRIPT_DIR}/logs/whisper_server.log"
}

find_whisper_bin() {
    WHISPER_BIN=""
    for candidate in \
        "${SCRIPT_DIR}/whisper.cpp/build/bin/whisper-server" \
        "${SCRIPT_DIR}/whisper.cpp/build/examples/server/whisper-server" \
        "$(which whisper-server 2>/dev/null)"; do
        if [ -x "${candidate}" ]; then
            WHISPER_BIN="${candidate}"
            return 0
        fi
    done
    return 1
}

start_whisper_server() {
    load_whisper_env
    if [ -f "${WHISPER_PID_FILE}" ] && kill -0 "$(cat "${WHISPER_PID_FILE}")" 2>/dev/null; then
        ok "whisper-server 已在运行 (PID: $(cat "${WHISPER_PID_FILE}"))"
        return 0
    fi

    if ! find_whisper_bin; then
        err "未找到 whisper-server 可执行文件，请先运行: ./scripts/setup-runtime.sh whisper"
        return 1
    fi
    if [ ! -f "${WHISPER_MODEL_PATH}" ]; then
        err "Whisper 模型文件不存在: ${WHISPER_MODEL_PATH}"
        err "请先运行: ./scripts/download-models.sh"
        return 1
    fi

    mkdir -p "$(dirname "${WHISPER_LOG_FILE}")"
    export LD_LIBRARY_PATH="${SCRIPT_DIR}/libs:$(dirname "${WHISPER_BIN}"):${LD_LIBRARY_PATH}"
    nohup "${WHISPER_BIN}" \
        --model "${WHISPER_MODEL_PATH}" \
        --language "${WHISPER_LANGUAGE}" \
        --port "${WHISPER_PORT}" \
        --host 127.0.0.1 \
        >> "${WHISPER_LOG_FILE}" 2>&1 &
    echo $! > "${WHISPER_PID_FILE}"
    ok "whisper-server 已启动 (PID: $!)"
    wait_for_url "http://127.0.0.1:${WHISPER_PORT}/" "whisper-server" 15 || return 1
}

start_llama_server() {
    bash llama_server.sh start || return 1
    wait_for_url "http://127.0.0.1:8080/health" "llama-server" 120
}

start_melotts() {
    local pid_file=".melotts.pid"
    mkdir -p logs
    if [ -f "${pid_file}" ] && kill -0 "$(cat "${pid_file}")" 2>/dev/null; then
        ok "MeloTTS 已在运行 (PID: $(cat "${pid_file}"))"
        return 0
    fi

    local melotts_py=""
    for candidate in \
        "${SCRIPT_DIR}/melotts-git/venv/bin/python" \
        "$(which python3 2>/dev/null)" \
        "$(which python 2>/dev/null)"; do
        if [ -x "${candidate}" ]; then
            melotts_py="${candidate}"
            break
        fi
    done

    if [ -z "${melotts_py}" ]; then
        warn "未找到 Python，MeloTTS 跳过（TTS 将降级静默）"
        return 0
    fi

    nohup "${melotts_py}" "${SCRIPT_DIR}/melotts-git/melo/tts_server.py" --port 8020 \
        >> "${SCRIPT_DIR}/logs/melotts.log" 2>&1 &
    echo $! > "${pid_file}"
    ok "MeloTTS 已启动 (PID: $!)"
    wait_for_url "http://127.0.0.1:8020/health" "MeloTTS" 60 || warn "MeloTTS 未响应（首次运行可能正在下载模型，TTS 暂时不可用）"
}

start_mock_qt() {
    local pid_file=".mock_qt.pid"
    if [ -f "${pid_file}" ] && kill -0 "$(cat "${pid_file}")" 2>/dev/null; then
        ok "mock-qt 已在运行 (PID: $(cat "${pid_file}"))"
        return 0
    fi

    local mock_py="mock-qt/venv/bin/python"
    if [ ! -x "${mock_py}" ]; then
        mock_py="$(which python3 2>/dev/null)"
    fi
    if [ -f "${SCRIPT_DIR}/mock-qt/server.py" ] && [ -n "${mock_py}" ]; then
        nohup "${mock_py}" "${SCRIPT_DIR}/mock-qt/server.py" --port 9000 \
            >> "${SCRIPT_DIR}/logs/mock_qt.log" 2>&1 &
        echo $! > "${pid_file}"
        ok "mock-qt 已启动 (PID: $!)"
        wait_for_url "http://127.0.0.1:9000/api/status" "mock-qt" 10 || warn "mock-qt 未响应"
    else
        warn "mock-qt 跳过（文件或 Python 不可用）"
    fi
}

start_backend() {
    local pid_file=".backend.pid"
    if is_port_listening 8000 && curl -ksf "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
        ok "backend 已在监听 :8000（运行中）"
        return 0
    fi
    if [ -f "${pid_file}" ] && kill -0 "$(cat "${pid_file}")" 2>/dev/null && is_port_listening 8000; then
        ok "backend 进程已在运行 (PID: $(cat "${pid_file}"))"
        wait_for_url "http://127.0.0.1:8000/health" "backend" 60 || warn "backend 进程存在但健康检查未通过，请查看 logs/backend.log"
        return 0
    fi
    if [ -f "${pid_file}" ] && kill -0 "$(cat "${pid_file}")" 2>/dev/null && ! is_port_listening 8000; then
        warn "backend PID 文件指向运行中进程但 :8000 未监听，清理旧 PID: $(cat "${pid_file}")"
        rm -f "${pid_file}"
    fi

    local backend_uvicorn="${SCRIPT_DIR}/backend/venv/bin/uvicorn"
    if [ ! -x "${backend_uvicorn}" ]; then
        err "backend venv 不存在，请先运行: ./scripts/setup-nx.sh"
        return 1
    fi

    mkdir -p "${SCRIPT_DIR}/logs"
    (
        cd "${SCRIPT_DIR}/backend" || exit 1
        setsid "${backend_uvicorn}" app.main:app \
            --host 0.0.0.0 --port 8000 --workers 1 \
            >> "${SCRIPT_DIR}/logs/backend.log" 2>&1 &
        echo $!
    ) > "${pid_file}"
    ok "backend 已启动 (PID: $(cat "${pid_file}"))"
    wait_for_url "http://127.0.0.1:8000/health" "backend" 60 || return 1
}

start_frontend_dev() {
    local pid_file=".frontend.pid"
    local lan_ip frontend_local_url frontend_lan_url frontend_wait_url frontend_env cert_pair cert_path key_path
    lan_ip=$(get_lan_ip)
    frontend_local_url="http://localhost:5173"
    frontend_lan_url="http://${lan_ip}:5173"
    frontend_wait_url="http://127.0.0.1:5173"
    frontend_env=""

    cert_pair="$(ensure_frontend_dev_cert "${lan_ip}")"
    if [ $? -eq 0 ]; then
        cert_path="${cert_pair%%|*}"
        key_path="${cert_pair##*|}"
        frontend_local_url="https://localhost:5173"
        frontend_lan_url="https://${lan_ip}:5173"
        frontend_wait_url="https://127.0.0.1:5173"
        frontend_env="USE_HTTPS=true SSL_CERT_PATH='${cert_path}' SSL_KEY_PATH='${key_path}'"
    fi

    if is_port_listening 5173; then
        if frontend_scheme_matches "${frontend_wait_url}"; then
            ok "frontend 已在监听 :5173（Vite 运行中）"
            if [ ! -f "${pid_file}" ]; then
                local re_pid
                re_pid="$(port_pids 5173 2>/dev/null | awk '{print $1}')"
                [ -n "${re_pid}" ] && echo "${re_pid}" > "${pid_file}"
            fi
        else
            warn "frontend 已监听 :5173，但当前协议与预期不一致"
            stop_port_processes 5173 "frontend" || warn "无法自动释放 :5173，请先停止旧的 Vite 进程后再重试"
        fi
    fi

    if is_port_listening 5173; then
        if ! frontend_scheme_matches "${frontend_wait_url}"; then
            warn "frontend 端口仍被占用，跳过重新启动"
        fi
    elif [ -d "${SCRIPT_DIR}/frontend/node_modules" ]; then
        rm -f "${pid_file}"
        nohup bash -c "cd '${SCRIPT_DIR}/frontend' && ${frontend_env} exec npx vite --host 0.0.0.0 --port 5173" \
            >> "${SCRIPT_DIR}/logs/frontend.log" 2>&1 &
        echo $! > "${pid_file}"
        ok "frontend 已启动 (PID: $!)"
        wait_for_url "${frontend_wait_url}" "frontend" 25 || warn "frontend 未响应（Vite 首次启动较慢，可稍后访问）"
    else
        warn "frontend/node_modules 不存在，请先运行: cd frontend && npm install"
    fi

    FRONTEND_LOCAL_URL="${frontend_local_url}"
    FRONTEND_LAN_URL="${frontend_lan_url}"
}

build_frontend_prod() {
    if [ ! -d "${SCRIPT_DIR}/frontend/node_modules" ]; then
        warn "frontend/node_modules 不存在，请先运行: cd frontend && npm install"
        warn "跳过构建，nginx 将继续使用旧的 dist/"
        return 0
    fi

    (
        cd "${SCRIPT_DIR}/frontend" || exit 1
        npx vite build >> "${SCRIPT_DIR}/logs/frontend_build.log" 2>&1
    )
    if [ $? -eq 0 ]; then
        ok "frontend 构建完成 → frontend/dist/"
        if command -v nginx &>/dev/null && pgrep -x nginx &>/dev/null; then
            nginx -s reload 2>/dev/null && ok "nginx 已重载，新前端已生效" || warn "nginx reload 失败，请手动执行: sudo nginx -s reload"
        else
            info "nginx 未运行，dist 已就绪，nginx 启动后将自动使用新版本"
        fi
    else
        err "frontend 构建失败，请检查 logs/frontend_build.log"
        return 1
    fi
}

check_service() {
    local name="$1" pid_file="$2" health_url="$3"
    local pid_status="停止" health_status=""

    if [ -f "${pid_file}" ]; then
        local pid
        pid=$(cat "${pid_file}")
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

print_status() {
    local frontend_health_url="https://127.0.0.1:5173"
    if ! curl -ksf "${frontend_health_url}" >/dev/null 2>&1; then
        frontend_health_url="http://127.0.0.1:5173"
    fi
    if [ ! -f ".frontend.pid" ]; then
        local frontend_pid
        frontend_pid=$(port_pids 5173 2>/dev/null | awk '{print $1}')
        [ -n "${frontend_pid}" ] && kill -0 "${frontend_pid}" 2>/dev/null && echo "${frontend_pid}" > ".frontend.pid"
    fi

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
    check_service "frontend"       ".frontend.pid"        "${frontend_health_url}"
    echo ""
    echo -e "${CYAN}日志目录: ${SCRIPT_DIR}/logs/${RESET}"
    if [ -d "logs" ]; then
        for f in logs/*.log; do
            [ -f "${f}" ] && printf "  %-30s  %s\n" "$(basename "${f}")" "$(wc -l < "${f}") 行"
        done
    fi
    echo ""
}
