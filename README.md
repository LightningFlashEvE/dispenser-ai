# dispenser-ai — 龙门机械臂粉末自动配料系统

## 项目概述

本项目面向龙门机械臂粉末称量、抓取、投料与混合场景，构建一套基于 **Jetson Orin NX 16GB 启用 Super Mode** 的全本地离线智能配料系统。系统采用"**AI理解 + 规则校验 + 控制执行**"分层架构，在本地完成语音识别、意图理解、语音合成、视觉检测、结构化任务生成、日志记录和网页服务，不依赖外网服务。

**一句话定义：**

**语音/界面输入 → ASR/表单 → LLM 生成任务级 JSON → 规则引擎校验 → 状态机检查 → 后级控制程序 → 机械臂/称重模块执行 → 结果反馈。**

### 核心特性

- **全本地离线**：ASR、LLM、TTS、视觉均在 Jetson 本地运行，不依赖云端
- **语音交互**：USB 麦克风 + whisper.cpp 语音识别 + MeloTTS 语音播报
- **AI 意图理解**：Qwen3-4B 大模型通过 llama.cpp 部署，理解自然语言配药指令
- **规则引擎校验**：所有任务经过规则引擎和状态机检查后才可执行
- **MCP Server 工具集**：将系统能力封装为标准工具，AI 可按需调用
- **工业触摸屏**：本地网页前端，支持触摸屏操作和局域网访问
- **实时天平推送**：MT-SICS 协议读取天平数据，WebSocket 实时推送前端
- **视觉工位检测**：固定 ROI + 二维码识别，自动识别工位药品和位置

---

## 快速开始

### 开发环境（推荐）

```bash
# 首次 clone 后先复制配置模板并下载外部模型资产
cp .env.example .env
./scripts/download-models.sh

# 一键启动全部服务（含 mock-qt 模拟后级 + Vite 开发服务器）
./scripts/start-all.sh

# 检查服务状态
./scripts/status.sh
```

> 模型、虚拟环境、编译产物、日志和本地数据库不进入 Git 仓库。完整说明见 [docs/assets.md](docs/assets.md)。

启动后访问：
- **前端**：http://localhost:5173
- **后端健康检查**：http://localhost:8000/health
- **MCP Server**：通过 stdio 模式接入 MCP Client

### MCP Client 配置

在支持 MCP 的工具中（如 Claude Desktop、Cursor、opencode 等），添加以下配置：

```json
{
  "mcpServers": {
    "dispenser-ai": {
      "command": "/home/lightning/dispenser-ai/mcp-server/venv/bin/python",
      "args": ["/home/lightning/dispenser-ai/mcp-server/server.py"]
    }
  }
}
```

### 单服务控制

```bash
# LLM 服务
./llama_server.sh start|stop|restart|status|logs

# ASR 服务
./scripts/start-whisper-server.sh start|stop|restart|status|logs

# 停止所有服务
./scripts/stop-all.sh
```

---

## 系统架构总览

### 分层架构

```
[ 本地网页前端 ] ←→ HTTP/REST + WebSocket ←→ [ FastAPI 后端 ]
                                               ↓ localhost HTTP/JSON
                                              [ 后端规则引擎 + 状态机 ]
                                               ↓ TCP + JSON
                                [ 后级控制程序（C++ / mock-qt）]
                                               ↓ CAN/RS485/串口/TCP
                                 [ 机械臂 / 称重模块 / 现场 IO ]

[ USB 麦克风 ] → [ VAD + whisper.cpp ] → [ LLM ] → [ 规则引擎 + 状态机 ]
[ 工业相机 ]   → [ 固定 ROI + QRCodeDetector ] → [ 工位/药品/坐标结果 ]
[ MeloTTS ]    → [ 语音反馈 ]

[ MCP Client ] → [ MCP Server (stdio) ] → HTTP 调用 → [ FastAPI 后端 ]
```

### 核心执行链路

```
语音/界面输入
  ↓
ASR（whisper.cpp）/ 表单输入
  ↓
LLM（llama.cpp server）→ intent_json（见 shared/intent_schema.json）
  ↓
规则引擎：校验 intent_json + 查药品库 → command JSON（见 shared/command_schema.json）
  ↓
状态机检查
  ↓
C++ 后级控制程序（TCP + JSON）
  ↓
机械臂 / 下料电机 / 现场 IO
  ↓
执行反馈 → 页面与语音反馈

天平数据流（并行常驻，仅展示）：
天平 WKC204C → RS422-USB → 后端 MT-SICS 驱动 → mg 整数 → WebSocket → 前端实时展示
（称重闭环由 C++ 自主决定，AI 层不干涉）
```

### 系统边界

#### Jetson 主控负责
- 本地语音识别（ASR）
- 本地大模型理解与任务级 JSON 生成
- 本地语音合成（TTS）
- 固定工位视觉识别、二维码识别与坐标换算
- 网页前后端服务
- 日志、配方、药品信息管理
- 与后级控制程序协议通信
- MCP Server 工具集

#### 后级控制程序负责
- 机械臂动作执行
- IO 联锁
- 称重闭环
- 急停和限位处理
- 动作顺序控制
- 超时与异常停机
- 执行结果状态反馈

#### 边界原则
- LLM **只输出任务级 JSON**，不直接生成底层运动控制指令
- 前端不直接控制设备
- 所有执行必须经过规则引擎、状态机和控制白名单约束
- 天平直连 Jetson，不经过 C++ 控制程序

详见 [docs/architecture.md](docs/architecture.md)

---

## 技术栈

| 模块 | 技术方案 | 说明 |
|------|----------|------|
| 主控平台 | Jetson Orin NX 16GB + Super Mode | 本地 AI 计算平台 |
| 语音识别 | whisper.cpp small / medium | 本地离线中文识别 |
| 大模型 | Qwen3-4B-Instruct-2507-Q4_K_M | llama.cpp server 部署（约 2.5GB 显存） |
| 语音合成 | MeloTTS | 本地离线 TTS |
| 视觉检测 | 固定 ROI + QRCodeDetector | 基础视觉方案 |
| 后端 | FastAPI | 本地 API 与页面服务 |
| 前端 | HTML / Vue | 本地网页、触摸屏访问 |
| MCP Server | Python mcp SDK + stdio | AI 工具调用层 |
| 数据存储 | SQLite + JSON | 轻量存储 |
| 控制通信 | HTTP/JSON + TCP | 与后级控制程序对接 |
| 天平通信 | MT-SICS over RS422-USB | 梅特勒 WKC204C 直连 |

---

## 开发环境与部署

> 以下为在 Jetson Orin NX 上从零部署的完整步骤，按顺序执行即可。

### 前置条件

- JetPack 6.x（Ubuntu 22.04 aarch64）已刷入，**Super Mode 已启用**
- Jetson 已联网（用于下载依赖和模型）
- 硬件已连接：天平（RS422-USB）、相机、麦克风

### 步骤 1：获取代码

```bash
# 方式一：git clone（推荐）
git clone <你的仓库地址> ~/dispenser-ai

# 方式二：直接复制目录
# 将整个 dispenser-ai 文件夹拷贝到/home/<user>/dispenser-ai
```

### 步骤 2：安装系统级依赖

推荐直接执行项目脚本：

```bash
cd ~/dispenser-ai
chmod +x scripts/*.sh llama_server.sh
./scripts/setup-nx.sh

# 编译/安装外部运行时：llama.cpp、whisper.cpp、MeloTTS
./scripts/setup-runtime.sh
```

`setup-nx.sh` 会安装 Ubuntu/JetPack 依赖、Node.js 20、后端 venv、MCP venv 和前端依赖。`setup-runtime.sh` 会恢复不进 Git 的外部运行时目录：`llama.cpp/`、`whisper.cpp/`、`melotts-git/`。

等价的核心系统依赖命令如下：

```bash
sudo apt update && sudo apt upgrade -y

sudo apt install -y \
    ca-certificates curl wget git git-lfs \
    build-essential cmake ninja-build pkg-config \
    python3 python3-venv python3-dev python3-pip \
    sqlite3 ffmpeg v4l-utils alsa-utils portaudio19-dev \
    libopencv-dev libopenblas-dev libsndfile1 \
    nginx net-tools

# Ubuntu 22.04 apt 源里的 Node 版本偏旧，Vite 5 建议 Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### 步骤 3：安装 Python 依赖（后端）

```bash
cd ~/dispenser-ai/backend
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
```

安装 MCP Server 依赖：

```bash
cd ~/dispenser-ai/mcp-server
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip wheel setuptools
./venv/bin/pip install -r requirements.txt
```

安装前端依赖：

```bash
cd ~/dispenser-ai/frontend
npm install
```

### 步骤 4：下载模型资产

模型文件不进 Git。脚本会把模型放到固定路径：

| 模型 | 是否自动 | 放置路径 |
|------|----------|----------|
| Qwen GGUF | 自动：默认使用 Hugging Face 稳定 `resolve/main` 地址；也可用 `QWEN_GGUF_URL` 覆盖 | `models/Qwen/Qwen3-4B-Instruct-2507-Q4_K_M.gguf` |
| Whisper base | 自动下载 | `models/whisper/ggml-base.bin` |
| Whisper small | 设置 `DOWNLOAD_WHISPER_SMALL=1` 后自动下载 | `models/whisper/ggml-small.bin` |

```bash
cd ~/dispenser-ai

# 默认会下载 Qwen；如 Hugging Face 不通，可用 QWEN_GGUF_URL 覆盖为 ModelScope、对象存储或内网镜像。
# export QWEN_GGUF_URL="<Qwen3-4B-Instruct-2507-Q4_K_M.gguf 的下载地址>"

# 默认下载 whisper base；如要 small，增加 DOWNLOAD_WHISPER_SMALL=1
DOWNLOAD_WHISPER_SMALL=1 ./scripts/download-models.sh
```

不要把 `cas-bridge.xethub.hf.co` 这类带 `X-Amz-Signature` 的临时链接写进仓库；它们通常会过期。脚本内置的是稳定的 `huggingface.co/.../resolve/main/...` 地址。

确认模型路径与 `backend/.env` 一致：

```env
LLM_MODEL_PATH=models/Qwen/Qwen3-4B-Instruct-2507-Q4_K_M.gguf
WHISPER_CPP_MODEL_PATH=models/whisper/ggml-small.bin
```

### 步骤 5：编译/安装外部运行时（推荐自动）

```bash
cd ~/dispenser-ai
./scripts/setup-runtime.sh
```

该脚本会自动完成：

| 组件 | 动作 | 输出位置 |
|------|------|----------|
| llama.cpp | clone + CUDA 编译 `llama-server` | `llama.cpp/build/bin/llama-server` |
| whisper.cpp | clone + CUDA 编译 `whisper-server` | `whisper.cpp/build/bin/whisper-server` |
| MeloTTS | clone + 创建 `melotts-git/venv` + 安装依赖 + 写入 HTTP wrapper | `melotts-git/venv/bin/python`、`melotts-git/melo/tts_server.py` |

只安装单个组件：

```bash
./scripts/setup-runtime.sh llama
./scripts/setup-runtime.sh whisper
./scripts/setup-runtime.sh melotts
```

如需更新已存在的外部仓库：

```bash
UPDATE_EXTERNAL=1 ./scripts/setup-runtime.sh
```

### 步骤 6：手动编译 llama.cpp（自动脚本失败时）

```bash
cd ~/dispenser-ai

git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
cmake -B build \
  -DGGML_CUDA=ON \
  -DCMAKE_CUDA_ARCHITECTURES=87 \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build --target llama-server -j$(nproc)

# 启动 LLM 服务（后台运行）
cd ~/dispenser-ai
./llama_server.sh start
```

> Orin NX GPU 架构为 Ampere，CUDA architecture 使用 `87`。新版 llama.cpp 使用 `DGGML_CUDA=ON`，不要再用旧参数 `DLLAMA_CUDA=ON`。

### 步骤 7：手动编译 whisper.cpp（自动脚本失败时）

```bash
cd ~/dispenser-ai
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
cmake -B build \
  -DGGML_CUDA=ON \
  -DWHISPER_BUILD_TESTS=OFF \
  -DCMAKE_CUDA_ARCHITECTURES=87 \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build --target whisper-server -j$(nproc)

# 启动 ASR HTTP 服务
cd ~/dispenser-ai
./scripts/start-whisper-server.sh start
```

### 步骤 8：手动安装 MeloTTS（自动脚本失败时）

```bash
cd ~/dispenser-ai
git clone https://github.com/myshell-ai/MeloTTS.git melotts-git
cd melotts-git
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
pip install -e .

# 首次初始化中文 TTS 资源
python3 -c "from melo.api import TTS; model = TTS(language='ZH')"
```

当前启动脚本会调用：

```bash
~/dispenser-ai/melotts-git/venv/bin/python ~/dispenser-ai/melotts-git/melo/tts_server.py --port 8020
```

`./scripts/setup-runtime.sh melotts` 会自动生成 `melotts-git/melo/tts_server.py`。如果手动安装原版 MeloTTS，必须同时提供这个 HTTP wrapper，否则后端无法访问 `/health`、`/speak`、`/synthesize`、`/stop`。

### 步骤 9：配置环境变量

```bash
cd ~/dispenser-ai/backend
cp .env.example .env

# 编辑 .env，按实际硬件情况修改以下关键项：
nano .env
```

**必须确认的配置项：**

| 配置项 | 说明 | 检查命令 |
|--------|------|---------|
| `BALANCE_SERIAL_PORT` | 天平串口路径 | `ls /dev/ttyUSB*` |
| `AUDIO_DEVICE_INDEX` | 麦克风设备索引 | `arecord -l` |
| `CAMERA_DEVICE_INDEX` | 相机设备索引 | `v4l2-ctl --list-devices` |
| `WHISPER_CPP_MODEL_PATH` | whisper 模型路径 | 步骤 5 编译后的路径 |
| `ENV` | 改为 `production` | - |
| `SKIP_CONFIRMATION` | 生产必须 `false` | - |

### 步骤 10：确认硬件设备

```bash
# 天平串口
ls -l /dev/ttyUSB0

# 摄像头
v4l2-ctl --list-devices

# 麦克风
arecord -l
python3 -c "import sounddevice as sd; print(sd.query_devices())"
```

### 步骤 11：启动服务

```bash
cd ~/dispenser-ai
./scripts/start-all.sh --prod
```

后端默认监听 `http://0.0.0.0:8000`。生产模式会跳过 `mock-qt` 和 Vite dev server，并构建前端 `frontend/dist/`。

### 步骤 12（可选）：配置开机自启（systemd）

创建 systemd 服务文件：

```bash
sudo nano /etc/systemd/system/dispenser-ai.service
```

写入以下内容（按实际路径修改）：

```ini
[Unit]
Description=Dispenser AI Backend
After=network.target llama-server.service

[Service]
Type=simple
User=<你的用户名>
WorkingDirectory=/home/<你的用户名>/dispenser-ai/backend
Environment="PATH=/home/<你的用户名>/dispenser-ai/backend/venv/bin"
ExecStart=/home/<你的用户名>/dispenser-ai/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable dispenser-ai
sudo systemctl start dispenser-ai
sudo systemctl status dispenser-ai
```

### 部署后联调清单

- [ ] 打开浏览器访问 `http://<Jetson-IP>:8000`，确认前端页面正常
- [ ] 语音输入 → 确认 ASR 转写正常
- [ ] LLM 对话 → 确认 llama.cpp server 推理正常
- [ ] 天平 → 确认前端能实时显示重量读数
- [ ] 相机 → 确认 ROI 检测和二维码识别正常
- [ ] C++ 后级控制程序 → 确认 TCP 通信和命令下发正常
- [ ] TTS → 确认语音播报正常

> 完整的版本升级与验收流程（含 WS 协议变更、pending_intent 验证、性能基线）见 [docs/upgrade-v0.2.md](docs/upgrade-v0.2.md)。

---

## MCP Server 工具集

MCP（Model Context Protocol）Server 将系统的核心能力封装为标准工具接口，AI 可通过 MCP 协议按需调用，实现**自然交互 + 选择性调用**的工作流。

### 工具清单

| 工具名 | 功能 | 调用示例 |
|--------|------|---------|
| `query_drug_stock` | 查询药品库存 | `query_drug_stock(keyword="氯化钠")` |
| `query_formulas` | 查询配方详情 | `query_formulas(keyword="生理盐水")` 或 `query_formulas(formula_id="F001")` |
| `query_device_status` | 查询设备状态 | `query_device_status()` |
| `query_stations` | 查询工位情况 | `query_stations(free_only=True)` |
| `query_tasks` | 查询任务历史 | `query_tasks(status="completed", limit=5)` |
| `query_system_resources` | 查询系统资源 | `query_system_resources()` |
| `generate_intent` | 自然语言 → intent JSON | `generate_intent(user_text="配500mg氯化钠")` |
| `build_command` | intent JSON → command JSON | `build_command(intent_json=..., drug_info=...)` |
| `send_command` | 下发 command 到控制层 | `send_command(command_json=...)` |
| `adjust_stock` | 调整药品库存 | `adjust_stock(reagent_code="NA001", delta_mg=10000)` |

### 典型交互流程

```
用户: "我要配 500mg 氯化钠"
AI: 调用 query_drug_stock("氯化钠") → 查到库存充足
AI: "找到氯化钠了，在 3 号工位，库存 50g。确认执行吗？"
用户: "确认"
AI: 调用 generate_intent("配500mg氯化钠") → 生成 intent JSON
AI: 调用 build_command(intent_json) → 生成 command JSON
AI: 调用 send_command(command_json) → 下发到控制层
AI: "已开始执行，预计 2 分钟完成"
```

### 启动方式

```bash
# 进入目录
cd mcp-server

# 安装依赖（首次运行）
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 复制环境变量
cp .env.example .env

# 启动 MCP Server（stdio 模式）
./venv/bin/python server.py
```

### 扩展新工具

在 `mcp-server/tools/` 下新建 Python 文件，实现 `register(mcp, backend_url)` 函数，使用 `@mcp.tool()` 装饰器定义工具，然后在 `server.py` 中导入并注册即可。

---

## 数据存储架构

本系统采用"**SQLite + JSON 文件**"的混合存储架构。

| 存储介质 | 数据类型 | 说明 |
|----------|---------|------|
| **SQLite** | 药品、配方、工位、任务、执行记录、报警记录 | 结构清晰、需要查询统计和关联分析的业务数据 |
| **JSON 文件** | 系统配置、标定参数、模型配置、规则模板、LLM 原始输出快照 | 层级较深、人工可读性要求较高的配置类数据 |

其中，SQLite 负责业务数据的规范化存储与可追溯查询，JSON 负责配置类和快照类数据的灵活管理与人工维护。高频实时控制状态原则上以内存态管理，必要时再按规则落库或落盘。

---

## 通信架构

### 前端 ↔ 后端
- `HTTP/REST + WebSocket`
- WebSocket 实时推送：天平读数、任务状态、语音转写、设备状态

### 后端 ↔ whisper-server（ASR HTTP 服务）
- 地址：`http://127.0.0.1:8081`
- 接口：`POST /inference`（上传 WAV 音频，返回转写结果）

### 后端 ↔ C++ 后级控制程序（TCP）
- `POST http://{CONTROL_ADAPTER_HOST}:{CONTROL_ADAPTER_PORT}/api/command`（下发 command JSON）
- `GET  http://{CONTROL_ADAPTER_HOST}:{CONTROL_ADAPTER_PORT}/api/status`（查询设备状态）
- `POST /api/tasks/callback`（C++ 回调 AI 层的执行结果）

### 后端 ↔ 天平（RS422-USB 串口）
- 串口设备：`BALANCE_SERIAL_PORT`（默认 `/dev/ttyUSB0`）
- 协议：MT-SICS ASCII，常用命令：`S`（稳定重量）、`SI`（即时重量）、`Z`（归零）

### 设备侧（C++ 控制程序负责）
- 电机驱动器：`RS485 + Modbus RTU`（或按实际驱动器协议）
- 其他现场设备：`CAN / 串口 / TCP`

---

## 运行态调度策略

### 服务分类

| 分类 | 服务 | 说明 |
|------|------|------|
| 常驻 | 视觉、后级控制通信、Web、控制适配层 | 持续运行，始终保持就绪 |
| 懒加载 | ASR、TTS | 按需启动，完成后释放资源 |
| 常驻 | LLM（llama.cpp server） | 常驻运行于 8080 端口 |

### 优先级（高 → 低）

| 优先级 | 服务 |
|--------|------|
| P0 | 后级控制通信与状态回读 |
| P1 | 视觉工位检测 |
| P2 | 网页状态显示 |
| P3 | ASR 语音识别 |
| P4 | TTS 语音合成 |
| P5 | LLM 深度推理 |
| P6 | 日志快照落盘 |

### 高负载降级顺序

`日志快照落盘` → `TTS` → `ASR` → `LLM 深度推理`

核心配料功能（后级控制通信、视觉检测）在降级期间保持运行。

### 互斥关系

| 互斥对 | 说明 |
|--------|------|
| LLM ↔ 其他 GPU 服务 | LLM 常驻运行，GPU 全时占用 |
| ASR ↔ TTS | 语音输入与输出不同时进行，避免回声 |
| 视觉检测 ↔ 相机参数调整 | 工位检测期间不允许修改 ROI/曝光参数 |

详见 [docs/architecture.md](docs/architecture.md)

---

## 目录结构

```
dispenser-ai/
├── README.md                     # 项目说明文档（本文件）
├── AGENTS.md                     # AI 施工导航文档
├── backend/                      # FastAPI 后端（AI、视觉、规则、状态机、天平驱动等）
│   ├── app/                      # 应用代码
│   │   ├── api/                  # REST API 路由
│   │   ├── models/               # 数据库 ORM 模型
│   │   ├── schemas/              # Pydantic Schema
│   │   ├── services/             # 业务逻辑层
│   │   │   ├── ai/               # AI 服务（LLM、ASR、TTS、对话、意图）
│   │   │   ├── device/           # 设备驱动（天平 MT-SICS、控制客户端）
│   │   │   ├── dialog/           # 对话系统（规则引擎、状态机、调度器）
│   │   │   ├── inventory/        # 药品库存管理
│   │   │   └── vision/           # 视觉检测服务
│   │   └── main.py               # FastAPI 入口
│   ├── .env.example              # 环境变量模板
│   └── requirements.txt          # Python 依赖
├── frontend/                     # Vue 前端（工业触摸屏与局域网访问界面）
├── mcp-server/                   # MCP Server（AI 工具调用层）
│   ├── server.py                 # MCP Server 入口
│   ├── tools/                    # MCP 工具实现
│   │   ├── base.py               # 工具基类
│   │   ├── query_drug_stock.py   # 查询药品库存
│   │   ├── query_device_status.py # 查询设备状态
│   │   ├── query_stations.py     # 查询工位情况
│   │   ├── query_tasks.py        # 查询任务历史
│   │   ├── generate_intent.py    # 自然语言 → intent JSON
│   │   ├── build_command.py      # intent JSON → command JSON
│   │   ├── send_command.py       # 下发 command 到控制层
│   │   └── adjust_stock.py       # 调整库存
│   ├── pyproject.toml
│   ├── requirements.txt
│   └── .env.example
├── shared/                       # Schema 契约文件
│   ├── intent_schema.json        # LLM 意图输出格式（v1.0）
│   └── command_schema.json       # 后级控制指令格式（v2.1）
├── mock-qt/                      # 模拟 C++ 后级控制程序（开发联调用）
├── libs/                         # 共享库目录（llama.cpp / whisper.cpp 编译产物）
├── docs/                         # 架构/协议/硬件文档
│   ├── architecture.md           # 系统架构设计
│   ├── command_protocol.md       # intent 与 command JSON 协议
│   ├── hardware_setup.md         # 硬件选型与部署
│   ├── llm_prompt_design.md      # LLM prompt 设计
│   └── upgrade-v0.2.md           # v0.2 重构升级手册
├── scripts/                      # 运维脚本
│   ├── start-all.sh              # 一键启动全部
│   ├── stop-all.sh               # 停止全部服务
│   ├── status.sh                 # 检查服务状态
│   └── start-whisper-server.sh   # 启动 ASR 服务
└── llama_server.sh               # llama.cpp server 控制脚本
```

---

## 关键设计原则

1. **本地优先**：核心链路不依赖外网
2. **任务级输出**：LLM 仅生成任务级 JSON，不直接生成底层运动控制指令
3. **规则先行**：所有任务先过规则引擎和状态机，未通过校验一律拒绝执行
4. **控制隔离**：后级控制程序负责把任务映射为设备动作，前端不直接控制设备
5. **安全优先**：急停、联锁、异常停机优先级高于 AI 决策
6. **可追溯**：日志、任务、异常和执行反馈全链路留痕
7. **信息不足先反问**：槽位缺失时必须先向用户确认，不得直接执行
8. **Schema 校验**：所有外部输入必须经过 Schema 校验

详见 [AGENTS.md](AGENTS.md) 中的绝对约束章节。

---

## 联系与协作

- AI 交互层（本仓库）：软件团队负责
- 后级控制程序：硬件/嵌入式/控制团队负责
- 对接接口文档：[docs/command_protocol.md](docs/command_protocol.md)
- 架构文档：[docs/architecture.md](docs/architecture.md)
