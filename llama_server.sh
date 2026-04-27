#!/bin/bash
# ============================================================
# llama_server.sh — llama.cpp server 启动/控制脚本
# 用途：控制本地 LLM 服务，供 backend 调用
# 部署目标：Jetson Orin NX (16GB, Super Mode)
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_BIN="${SCRIPT_DIR}/llama.cpp/build/bin/llama-server"
# 当前模型：Qwen3-4B-Instruct-2507-Q4_K_M（约 2.5GB）
# 可通过环境变量 MODEL_PATH 覆盖默认路径。
MODEL_PATH="${MODEL_PATH:-${SCRIPT_DIR}/models/Qwen/Qwen3-4B-Instruct-2507-Q4_K_M.gguf}"
PID_FILE="${SCRIPT_DIR}/.llama_server.pid"
LOG_FILE="${SCRIPT_DIR}/logs/llama_server.log"

# === 可调参数 ===
PORT=8080
CONTEXT_LENGTH=4096
GPU_LAYERS=99
TEMPERATURE=0.6
TOP_P=0.9
THREADS=6
CACHE_K_TYPE="q8_0"
CACHE_V_TYPE="q8_0"
# chat template 通过 --jinja 读取 GGUF 内嵌模板，不再硬编码
# --reasoning off：明确禁用 thinking 模式（当前为非思考 Instruct 模型）

# === 确保 CUDA 路径 ===
export PATH="/usr/local/cuda/bin:${PATH}"
export CUDACXX="/usr/local/cuda/bin/nvcc"

# === 函数 ===
usage() {
    echo "用法: $0 {start|stop|restart|status|logs}"
    echo ""
    echo "  start   - 启动 llama.cpp server"
    echo "  stop    - 停止 llama.cpp server"
    echo "  restart - 重启 llama.cpp server"
    echo "  status  - 查看运行状态"
    echo "  logs    - 查看日志输出"
    exit 1
}

check_prerequisites() {
    if [ ! -f "${SERVER_BIN}" ]; then
        echo "错误: llama-server 未编译，请先运行: cd llama.cpp && cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=87 && cmake --build build --target llama-server -j\$(nproc)"
        exit 1
    fi

    if [ ! -f "${MODEL_PATH}" ]; then
        echo "错误: 模型文件不存在: ${MODEL_PATH}"
        exit 1
    fi

    mkdir -p "$(dirname "${LOG_FILE}")"
}

is_running() {
    if [ -f "${PID_FILE}" ]; then
        local pid=$(cat "${PID_FILE}")
        if kill -0 "${pid}" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

do_start() {
    if is_running; then
        echo "llama.cpp server 已在运行 (PID: $(cat "${PID_FILE}"))"
        return 0
    fi

    echo "正在启动 llama.cpp server..."
    echo "  模型: ${MODEL_PATH}"
    echo "  端口: ${PORT}"
    echo "  上下文: ${CONTEXT_LENGTH}"
    echo "  GPU 层: ${GPU_LAYERS}"

    nohup "${SERVER_BIN}" \
        -m "${MODEL_PATH}" \
        --port "${PORT}" \
        --ctx-size "${CONTEXT_LENGTH}" \
        --n-gpu-layers "${GPU_LAYERS}" \
        --parallel 1 \
        --temp "${TEMPERATURE}" \
        --top-p "${TOP_P}" \
        --threads "${THREADS}" \
        --threads-batch 4 \
        --cache-type-k "${CACHE_K_TYPE}" \
        --cache-type-v "${CACHE_V_TYPE}" \
        --jinja \
        --reasoning off \
        --no-warmup \
        --host 127.0.0.1 \
        --api-key "none" \
        >> "${LOG_FILE}" 2>&1 &

    local pid=$!
    echo "${pid}" > "${PID_FILE}"
    echo "llama.cpp server 已启动 (PID: ${pid})"
    echo "日志: tail -f ${LOG_FILE}"

    # 等待服务就绪
    echo "等待服务就绪..."
    for i in $(seq 1 30); do
        if curl -s "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
            echo "服务已就绪 (http://127.0.0.1:${PORT})"
            return 0
        fi
        sleep 1
    done

    echo "警告: 服务启动可能较慢，请检查日志: ${LOG_FILE}"
}

do_stop() {
    if ! is_running; then
        echo "llama.cpp server 未在运行"
        rm -f "${PID_FILE}"
        return 0
    fi

    local pid=$(cat "${PID_FILE}")
    echo "正在停止 llama.cpp server (PID: ${pid})..."
    kill "${pid}" 2>/dev/null

    # 等待进程结束
    for i in $(seq 1 10); do
        if ! kill -0 "${pid}" 2>/dev/null; then
            echo "llama.cpp server 已停止"
            rm -f "${PID_FILE}"
            return 0
        fi
        sleep 1
    done

    echo "强制终止..."
    kill -9 "${pid}" 2>/dev/null
    rm -f "${PID_FILE}"
    echo "llama.cpp server 已强制停止"
}

do_status() {
    if is_running; then
        local pid=$(cat "${PID_FILE}")
        echo "状态: 运行中 (PID: ${pid})"
        echo "端口: ${PORT}"
        echo "内存使用: $(ps -o rss= -p ${pid} 2>/dev/null | awk '{printf "%.1fMB", $1/1024}')"

        # 检查健康端点
        if curl -s "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
            echo "健康检查: 通过"
        else
            echo "健康检查: 未响应"
        fi
    else
        echo "状态: 停止"
    fi
}

do_logs() {
    if [ -f "${LOG_FILE}" ]; then
        tail -f "${LOG_FILE}"
    else
        echo "日志文件不存在: ${LOG_FILE}"
    fi
}

# === 主逻辑 ===
case "$1" in
    start)
        check_prerequisites
        do_start
        ;;
    stop)
        do_stop
        ;;
    restart)
        check_prerequisites
        do_stop
        sleep 2
        do_start
        ;;
    status)
        do_status
        ;;
    logs)
        do_logs
        ;;
    *)
        usage
        ;;
esac
