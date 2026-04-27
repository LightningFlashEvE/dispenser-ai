# 大资产分发说明

本仓库只提交源码、文档、Schema、配置模板和运维脚本。模型、虚拟环境、编译产物、日志、本地数据库等运行态资产不进入 Git。

## 不进入 Git 的内容

| 路径 | 原因 | 恢复方式 |
|------|------|----------|
| `models/` | LLM/ASR 模型体积大，部分文件超过 GitHub/LFS 常规限制 | 执行 `scripts/download-models.sh` 或 `scripts/download-models.ps1` |
| `libs/` | Jetson 编译产物与目标机环境强相关 | 在目标机编译，或从 Release/对象存储下载 |
| `llama.cpp/` | 外部项目源码和构建目录 | 按 README 或部署脚本 clone/build |
| `whisper.cpp/` | 外部项目源码和构建目录 | 按 README 或部署脚本 clone/build |
| `melotts-git/` | 外部 TTS 项目和 Python 环境 | 按 README 安装 |
| `**/venv/` | 本机 Python 虚拟环境 | `python3.11 -m venv venv && pip install -r requirements.txt` |
| `**/node_modules/` | Node 依赖缓存 | `npm install` |
| `data/*.db`、`backend/data/*.db` | 本地业务数据，可能包含现场状态 | 由初始化流程创建或导入示例数据 |
| `logs/`、`*.pid` | 运行态文件 | 服务启动后自动生成 |

## 推荐下载位置

### Qwen GGUF

默认路径：

```text
models/Qwen/Qwen3-4B-Instruct-2507-Q4_K_M.gguf
```

该文件当前约 2.4GB，不适合直接进入 Git。推荐放在 Hugging Face、ModelScope、对象存储或 GitHub Release 分卷资产中，然后在下载脚本中配置 URL 和 SHA256。

### Whisper 模型

默认路径：

```text
models/whisper/ggml-base.bin
models/whisper/ggml-small.bin
```

可从 `ggml-org/whisper.cpp` 的公开模型资产下载。

## 用户恢复流程

```bash
git clone https://github.com/LightningFlashEvE/dispenser-ai.git
cd dispenser-ai
cp .env.example .env
./scripts/download-models.sh
./scripts/start-all.sh
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
