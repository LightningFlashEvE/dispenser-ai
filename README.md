# dispenser-ai — 龙门机械臂粉末自动配料系统

## 项目概述

本项目面向龙门机械臂粉末称量、抓取、投料与混合场景，构建一套基于 **Jetson Orin NX 16GB 启用 Super Mode** 的全本地离线智能配料系统。系统采用"**AI理解 + 规则校验 + 控制执行**"分层架构，在本地完成语音识别、意图理解、语音合成、视觉检测、结构化任务生成、日志记录和网页服务，不依赖外网服务。

**一句话定义：**

**语音/界面输入 → ASR/表单 → LLM 生成任务级 JSON → 规则引擎校验 → 状态机检查 → 后级控制程序 → 机械臂/称重模块执行 → 结果反馈。**

---

## 开发环境与部署目标

| 项目 | 规格 |
|------|------|
| **开发环境** | Windows(x86_64)，通过 Ollama(Windows) + mock-qt 完成核心业务逻辑开发 |
| **部署目标** | 英伟达 **Jetson Orin NX Super 开发板 16GB RAM + 512GB NVMe SSD** |
| **系统** | JetPack 6.x（Ubuntu 22.04 aarch64），启用 Super Mode |

### 开发阶段 vs 部署阶段功能差异

| 模块 | Windows 开发阶段 | Jetson 部署阶段 |
|------|-----------------|----------------|
| Ollama LLM | ✅ Windows 版，qwen2.5:7b | ✅ aarch64 版 |
| ASR (whisper.cpp) | ❌ 跳过，待部署后实现 | ✅ 编译 ARM64 版本 |
| TTS (MeloTTS) | ❌ 跳过，待部署后实现 | ✅ Linux 部署 |
| 天平驱动 (MT-SICS) | ❌ 跳过，无串口设备 | ✅ pyserial + /dev/ttyUSB0 |
| 视觉检测 | ❌ 跳过，依赖相机硬件 | ✅ OpenCV |
| 规则引擎 / 状态机 | ✅ 纯 Python 逻辑 | ✅ 相同代码 |
| 控制通信 (HTTP) | ✅ mock-qt (FastAPI) | 替换为真实 C++ 控制程序 |
| REST API / WebSocket | ✅ 全部实现 | ✅ 相同代码 |
| 前端 | ✅ 全部实现 | ✅ 相同代码 |

### Windows 开发注意事项

1. **所有路径使用 `pathlib.Path`**，禁止硬编码正反斜杠
2. **音频/串口设备路径按平台区分**（COMx vs /dev/ttyUSBx）
3. **whisper.cpp 使用 subprocess 调用独立可执行文件**，不用 Python 绑定（ARM64 wheel 不兼容）
4. **mock-qt 用 HTTP 接口**，部署时替换为真实 C++ 控制程序的 TCP 通信
5. **Ollama 确认 `qwen2.5:7b` 在 aarch64 上可用**后再定死模型

---

## Jetson 开发板部署指南

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

```bash
sudo apt update && sudo apt upgrade -y

sudo apt install -y \
    python3.11 python3.11-venv python3-pip \
    nodejs npm sqlite3 \
    git curl wget ffmpeg v4l-utils alsa-utils \
    libopencv-dev pkg-config
```

### 步骤 3：安装 Python 依赖（后端）

```bash
cd ~/dispenser-ai/backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 步骤 4：安装 Ollama 并拉取模型

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 下载 LLM 模型（约 4-6GB，需联网）
ollama pull qwen2.5:7b

# 设置 Ollama 服务开机自启并配置推理后释放 GPU
sudo systemctl enable ollama
# 编辑 /etc/systemd/system/ollama.service，在 [Service] 段添加：
# Environment="OLLAMA_KEEP_ALIVE=300"
# 然后重载：
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

### 步骤 5：编译 whisper.cpp（ARM64）

```bash
cd ~
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
cmake -B build -DWHISPER_BUILD_EXAMPLES=OFF
cmake --build build --config Release -j$(nproc)

# 下载语音模型（small 或 medium）
# ggml-small.bin  (约 466 MB) 或 ggml-medium.bin (约 1.5 GB)
wget -O models/ggml-small.bin https://huggingface.co/ggml-org/whisper.cpp/resolve/main/ggml-model-whisper-small.bin

# 记住可执行文件和模型路径，后面配置要用：
# 可执行文件: ~/whisper.cpp/build/bin/main
# 模型文件:   ~/whisper.cpp/models/ggml-small.bin
```

### 步骤 6：安装 MeloTTS

```bash
pip install MeloTTS

# 下载模型（首次运行会自动下载，也可手动指定路径）
python3 -c "from melo.api import TTS; model = TTS(language='ZH')"
```

### 步骤 7：配置环境变量

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

### 步骤 8：确认硬件设备

```bash
# 天平串口
ls -l /dev/ttyUSB0

# 摄像头
v4l2-ctl --list-devices

# 麦克风
arecord -l
python3 -c "import sounddevice as sd; print(sd.query_devices())"
```

### 步骤 9：启动后端服务

```bash
cd ~/dispenser-ai/backend
source venv/bin/activate
python main.py
```

启动成功后，默认监听 `http://0.0.0.0:8000`，可通过浏览器或工业触摸屏访问。

### 步骤 10（可选）：配置开机自启（systemd）

创建 systemd 服务文件：

```bash
sudo nano /etc/systemd/system/dispenser-ai.service
```

写入以下内容（按实际路径修改）：

```ini
[Unit]
Description=Dispenser AI Backend
After=network.target ollama.service

[Service]
Type=simple
User=<你的用户名>
WorkingDirectory=/home/<你的用户名>/dispenser-ai/backend
Environment="PATH=/home/<你的用户名>/dispenser-ai/backend/venv/bin"
ExecStart=/home/<你的用户名>/dispenser-ai/backend/venv/bin/python main.py
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
- [ ] LLM 对话 → 确认 Ollama 推理正常
- [ ] 天平 → 确认前端能实时显示重量读数
- [ ] 相机 → 确认 ROI 检测和二维码识别正常
- [ ] C++ 后级控制程序 → 确认 TCP 通信和命令下发正常
- [ ] TTS → 确认语音播报正常

---

## 系统边界

### Jetson 主控负责
- 本地语音识别（ASR）
- 本地大模型理解与任务级 JSON 生成
- 本地语音合成（TTS）
- 固定工位视觉识别、二维码识别与坐标换算
- 网页前后端服务
- 日志、配方、药品信息管理
- 与后级控制程序协议通信

### 后级控制程序负责
- 机械臂动作执行
- IO 联锁
- 称重闭环
- 急停和限位处理
- 动作顺序控制
- 超时与异常停机
- 执行结果状态反馈

### 边界原则
- LLM **只输出任务级 JSON**
- LLM **不直接生成底层运动控制指令**
- 前端不直接控制设备
- 所有执行必须经过规则引擎、状态机和控制白名单约束

---

## 系统架构总览

```
[ 本地网页前端 ] ←→ HTTP/REST + WebSocket ←→ [ FastAPI 后端 ]
                                              ↓ localhost HTTP/JSON
                               [ 控制适配层 / 后级控制程序 ]
                                              ↓ CAN / RS485 / 串口 / TCP
                                [ 机械臂 / 称重模块 / 现场 IO ]

[ USB 麦克风 ] → [ VAD + whisper.cpp ] → [ LLM ] → [ 规则引擎 + 状态机 ]
[ 工业相机 ] → [ 固定 ROI + QRCodeDetector ] → [ 工位/药品/坐标结果 ]
[ MeloTTS ] → [ 语音反馈 ]
```

详见 [docs/architecture.md](docs/architecture.md)

---

## 技术栈

| 模块 | 技术方案 | 说明 |
|------|----------|------|
| 主控平台 | Jetson Orin NX 16GB + Super Mode | 本地 AI 计算平台 |
| 语音识别 | whisper.cpp small / medium | 本地离线中文识别 |
| 大模型 | Gemma 4 E4B、Qwen2.5-3B/7B、Phi-3 Mini 候选 | 结构化任务生成 |
| 语音合成 | MeloTTS | 本地离线 TTS |
| 视觉检测 | 固定 ROI + QRCodeDetector | 基础视觉方案 |
| 后端 | FastAPI | 本地 API 与页面服务 |
| 前端 | HTML / Vue | 本地网页、触摸屏访问 |
| 数据存储 | SQLite + JSON | 轻量存储 |
| 控制通信 | CAN / RS485 / 串口 / TCP | 与后级控制程序对接 |

---

## 数据存储架构

本系统采用“**SQLite + JSON 文件**”的混合存储架构。

- **SQLite**：用于保存药品、配方、工位、任务、执行记录、报警记录等结构清晰、需要查询统计和关联分析的业务数据
- **JSON 文件**：用于保存系统配置、标定参数、模型配置、规则模板以及 LLM 原始输出快照等层级较深、人工可读性要求较高的数据

其中，SQLite 负责业务数据的规范化存储与可追溯查询，JSON 负责配置类和快照类数据的灵活管理与人工维护。高频实时控制状态原则上以内存态管理，必要时再按规则落库或落盘。该方案兼顾了 Jetson 边缘设备本地部署场景下的低运维成本、数据可追溯性、配置可维护性和故障复盘能力。

---

## 通信架构

### 前端 ↔ 后端
- `HTTP/REST + WebSocket`

### 后端 ↔ 控制适配层 / 后级控制程序
- `localhost HTTP/REST + JSON`

### 后级控制程序 ↔ 设备执行层
- `CAN / RS485 / 串口 / TCP`
- 电机、称重和现场设备可采用 `RS485 + Modbus RTU / Modbus TCP`

---

## 运行态调度策略

### 服务分类

| 分类 | 服务 | 说明 |
|------|------|------|
| 常驻 | 视觉、后级控制通信、Web、控制适配层 | 持续运行，始终保持就绪 |
| 懒加载 | ASR、TTS | 按需启动，完成后释放资源 |
| 半常驻 | LLM | 推理期间独占 GPU |

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
| LLM ↔ 其他 GPU 服务 | LLM 推理期间 GPU 独占 |
| ASR ↔ TTS | 语音输入与输出不同时进行，避免回声 |
| 视觉检测 ↔ 相机参数调整 | 工位检测期间不允许修改 ROI/曝光参数 |

详见 [docs/architecture.md](docs/architecture.md)

---

## 目录结构

```
dispenser-ai/
├── README.md
├── AGENTS.md
├── backend/
├── frontend/
├── shared/
├── mock-qt/
└── docs/
```

---

## 关键设计原则

1. **本地优先**：核心链路不依赖外网
2. **任务级输出**：LLM 仅生成任务级 JSON
3. **规则先行**：所有任务先过规则引擎和状态机
4. **控制隔离**：后级控制程序负责把任务映射为设备动作
5. **安全优先**：急停、联锁、异常停机优先级高于 AI 决策
6. **可追溯**：日志、任务、异常和执行反馈全链路留痕

---

## 联系与协作

- AI 交互层（本仓库）：软件团队负责
- 后级控制程序：硬件/嵌入式/控制团队负责
- 对接接口文档：[docs/command_protocol.md](docs/command_protocol.md)
- 架构文档：[docs/architecture.md](docs/architecture.md)
