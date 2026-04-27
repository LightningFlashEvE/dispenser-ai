#!/bin/bash
# ============================================================
# start-whisper-server.sh — whisper.cpp HTTP 服务启动脚本
# 接口：POST http://127.0.0.1:8081/inference（上传 WAV，返回转写结果）
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${SCRIPT_DIR}/.whisper_server.pid"
LOG_FILE="${SCRIPT_DIR}/logs/whisper_server.log"

# 从 .env 读取配置（若存在）
ENV_FILE="${SCRIPT_DIR}/backend/.env"
if [ -f "${ENV_FILE}" ]; then
    export $(grep -E '^(WHISPER_SERVER_URL|WHISPER_CPP_MODEL_PATH|WHISPER_LANGUAGE|AUDIO_SAMPLE_RATE)=' "${ENV_FILE}" | xargs 2>/dev/null)
fi

# 可配置参数
PORT="${WHISPER_PORT:-8081}"
MODEL_PATH="${WHISPER_CPP_MODEL_PATH:-${SCRIPT_DIR}/models/whisper/ggml-base.bin}"
LANGUAGE="${WHISPER_LANGUAGE:-zh}"

# 查找 whisper-server 可执行文件
WHISPER_BIN=""
for candidate in \
    "${SCRIPT_DIR}/whisper.cpp/build/bin/whisper-server" \
    "${SCRIPT_DIR}/whisper.cpp/build/examples/server/whisper-server" \
    "$(which whisper-server 2>/dev/null)"; do
    if [ -x "${candidate}" ]; then
        WHISPER_BIN="${candidate}"
        break
    fi
done

usage() {
    echo "用法: $0 {start|stop|restart|status|logs}"
    exit 1
}

is_running() {
    [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null
}

do_start() {
    if is_running; then
        echo "whisper-server 已在运行 (PID: $(cat "${PID_FILE}"))"
        return 0
    fi

    if [ -z "${WHISPER_BIN}" ]; then
        echo "错误: 未找到 whisper-server 可执行文件"
        echo "  请先编译（whisper.cpp HTTP server 示例）："
        echo "    cd whisper.cpp"
        echo "    cmake -B build -DGGML_CUDA=ON -DWHISPER_BUILD_TESTS=OFF -DCMAKE_CUDA_ARCHITECTURES=87"
        echo "    cmake --build build --target whisper-server --config Release -j\$(nproc)"
        echo "  编译后可执行文件在: whisper.cpp/build/bin/whisper-server"
        exit 1
    fi

    if [ ! -f "${MODEL_PATH}" ]; then
        echo "错误: 模型文件不存在: ${MODEL_PATH}"
        echo "  请下载: wget -O ${MODEL_PATH} https://huggingface.co/ggml-org/whisper.cpp/resolve/main/ggml-base.bin"
        exit 1
    fi

    mkdir -p "$(dirname "${LOG_FILE}")"
    echo "正在启动 whisper-server..."
    echo "  模型: ${MODEL_PATH}"
    echo "  端口: ${PORT}"
    echo "  语言: ${LANGUAGE}"

    export LD_LIBRARY_PATH="${SCRIPT_DIR}/libs:$(dirname "${WHISPER_BIN}"):${LD_LIBRARY_PATH}"
    nohup "${WHISPER_BIN}" \
        --model "${MODEL_PATH}" \
        --language "${LANGUAGE}" \
        --port "${PORT}" \
        --host 127.0.0.1 \
        2>&1 >> "${LOG_FILE}" &

    local pid=$!
    echo "${pid}" > "${PID_FILE}"
    echo "whisper-server 已启动 (PID: ${pid})"

    # 等待就绪（最多 15 秒）
    echo "等待就绪..."
    for i in $(seq 1 15); do
        if curl -sf "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
            echo "就绪 (http://127.0.0.1:${PORT})"
            return 0
        fi
        sleep 1
    done
    echo "警告: 服务启动超时，请检查日志: ${LOG_FILE}"
}

do_stop() {
    if ! is_running; then
        echo "whisper-server 未在运行"
        rm -f "${PID_FILE}"
        return 0
    fi
    local pid=$(cat "${PID_FILE}")
    echo "停止 whisper-server (PID: ${pid})..."
    kill "${pid}" 2>/dev/null
    for i in $(seq 1 8); do
        kill -0 "${pid}" 2>/dev/null || { rm -f "${PID_FILE}"; echo "已停止"; return 0; }
        sleep 1
    done
    kill -9 "${pid}" 2>/dev/null
    rm -f "${PID_FILE}"
    echo "已强制停止"
}

case "$1" in
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_stop; sleep 1; do_start ;;
    status)
        if is_running; then
            echo "状态: 运行中 (PID: $(cat "${PID_FILE}"))  端口: ${PORT}"
            curl -sf "http://127.0.0.1:${PORT}/" >/dev/null 2>&1 && echo "健康检查: 通过" || echo "健康检查: 未响应"
        else
            echo "状态: 停止"
        fi
        ;;
    logs)
        [ -f "${LOG_FILE}" ] && tail -f "${LOG_FILE}" || echo "日志文件不存在: ${LOG_FILE}"
        ;;
    *) usage ;;
esac
