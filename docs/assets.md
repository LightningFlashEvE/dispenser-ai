# 大资产分发说明

本仓库只提交源码、文档、Schema、配置模板和运维脚本。模型、虚拟环境、编译产物、日志、本地数据库等运行态资产不进入 Git。

## 不进入 Git 的内容

| 路径 | 原因 | 恢复方式 |
|------|------|----------|
| `models/` | LLM/ASR 模型体积大，部分文件超过 GitHub/LFS 常规限制 | 执行 `scripts/download-models.sh` 或 `scripts/download-models.ps1` |
| `libs/` | Jetson 编译产物与目标机环境强相关 | 在目标机编译，或从 Release/对象存储下载 |
| `llama.cpp/` | 外部项目源码和构建目录 | 执行 `scripts/setup-runtime.sh llama` |
| `whisper.cpp/` | 外部项目源码和构建目录 | 执行 `scripts/setup-runtime.sh whisper` |
| `melotts-git/` | 外部 TTS 项目和 Python 环境 | 执行 `scripts/setup-runtime.sh melotts` |
| `**/venv/` | 本机 Python 虚拟环境 | `python3 -m venv venv && pip install -r requirements.txt` |
| `**/node_modules/` | Node 依赖缓存 | `npm install` |
| `data/*.db`、`backend/data/*.db` | 本地业务数据，可能包含现场状态 | 由初始化流程创建或导入示例数据 |
| `logs/`、`*.pid` | 运行态文件 | 服务启动后自动生成 |

## 推荐下载位置

### Qwen GGUF

默认路径：

```text
models/Qwen/Qwen3-4B-Instruct-2507-Q4_K_M.gguf
```

该文件当前约 2.4GB，不适合直接进入 Git。脚本默认使用 Hugging Face 稳定 `resolve/main` 地址下载到固定路径；如 Hugging Face 不通，可用 ModelScope、对象存储或内网镜像地址覆盖：

```bash
# 可选覆盖；默认不需要设置
export QWEN_GGUF_URL="<Qwen3-4B-Instruct-2507-Q4_K_M.gguf 下载地址>"
./scripts/download-models.sh
```

不要把 `cas-bridge.xethub.hf.co` 这类带 `X-Amz-Signature` 的临时签名链接写进仓库；它们通常会过期，只适合临时作为 `QWEN_GGUF_URL` 使用。

### Whisper 模型

默认路径：

```text
models/whisper/ggml-base.bin
models/whisper/ggml-small.bin
```

`ggml-base.bin` 默认自动下载；`ggml-small.bin` 需要显式开启：

```bash
DOWNLOAD_WHISPER_SMALL=1 ./scripts/download-models.sh
```

## 外部运行时目录

推荐自动恢复：

```bash
./scripts/setup-runtime.sh
```

恢复后目录如下：

| 目录 | 关键文件 |
|------|----------|
| `llama.cpp/` | `llama.cpp/build/bin/llama-server` |
| `whisper.cpp/` | `whisper.cpp/build/bin/whisper-server` |
| `melotts-git/` | `melotts-git/venv/bin/python`、`melotts-git/melo/tts_server.py` |

`melotts-git/melo/tts_server.py` 是本项目需要的 HTTP wrapper，提供 `/health`、`/speak`、`/synthesize`、`/stop`。如果使用原版 MeloTTS 手动安装，仍需补上这个 wrapper。

## 用户恢复流程

```bash
git clone https://github.com/LightningFlashEvE/dispenser-ai.git
cd dispenser-ai
cp .env.example .env
./scripts/setup-nx.sh
./scripts/setup-runtime.sh
./scripts/download-models.sh
./scripts/start-dev.sh
```

Windows PowerShell：

```powershell
git clone https://github.com/LightningFlashEvE/dispenser-ai.git
cd dispenser-ai
Copy-Item .env.example .env
.\scripts\download-models.ps1
```

## 校验建议

为每个外部分发资产记录 SHA256。模型更新时同步更新下载脚本、本文档和部署说明，避免用户下载到不匹配的模型。
