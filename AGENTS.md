# AGENTS.md — dispenser-ai 项目 AI 施工导航

> 本文件是整个项目的 AI 编码导航总入口。
> 进入任何子模块施工前，**必须先读本文件**，再读对应子目录的 AGENTS.md。

---

## 项目一句话定义

本项目是一个基于 **Jetson Orin NX 16GB 启用 Super Mode** 的龙门机械臂粉末自动配料系统软件平台，采用“**AI理解 + 规则校验 + 控制执行**”架构，支持本地离线语音交互、固定工位视觉识别、任务级 JSON 生成和后级控制程序联动。

---

## 模块地图

| 目录 | 职责 | 施工指南 |
|------|------|---------|
| `backend/` | FastAPI 后端，负责 AI、视觉、规则、状态机、天平驱动、数据与协议通信 | [backend/AGENTS.md](backend/AGENTS.md) |
| `frontend/` | 本地网页前端，工业触摸屏与局域网访问界面 | [frontend/AGENTS.md](frontend/AGENTS.md) |
| `mcp-server/` | MCP Server，将系统能力封装为 AI 可调用的工具 | 见下方 MCP Server 说明 |
| `shared/` | Schema 契约文件（intent_schema.json + command_schema.json） | 见下方 Schema 说明 |
| `mock-qt/` | 模拟 C++ 后级控制程序，用于开发联调 | [mock-qt/AGENTS.md](mock-qt/AGENTS.md) |
| `libs/` | 项目级共享库目录（llama.cpp / whisper.cpp 编译产物 `.so`） | 便于整机迁移，无需目标机重新编译 |
| `docs/` | 架构/协议/硬件文档 | 见下方文档索引 |

---

## Schema 文件说明（`shared/`）

| 文件 | 用途 | 版本 |
|------|------|------|
| `shared/intent_schema.json` | LLM 输出的意图 JSON 格式，AI 层内部流转，规则引擎校验用 | v1.0 |
| `shared/command_schema.json` | 下发给 C++ 控制程序的执行指令格式，双方接口契约 | v2.1 |

**两个 Schema 的区别：**
- `intent_schema`：语义层，字段允许 null（表示用户未提供），LLM 填写，不保证业务正确性
- `command_schema`：执行层，字段来自数据库，规则引擎填写，所有字段必须合法且通过校验

---

## 文档索引

| 文档 | 用途 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 系统分层、边界、执行链路、天平数据流说明 |
| [docs/command_protocol.md](docs/command_protocol.md) | intent_json 与 command JSON 协议完整说明 |
| [docs/hardware_setup.md](docs/hardware_setup.md) | 硬件选型（含天平 WKC204C）、部署、运维与排障 |
| [docs/llm_prompt_design.md](docs/llm_prompt_design.md) | LLM system prompt 模板、工位快照注入、对话历史格式、典型场景示例、后端实现要点 |
| [docs/upgrade-v0.2.md](docs/upgrade-v0.2.md) | v0.2 重构升级手册（破坏性变更说明、Jetson 升级步骤、验收清单、回滚方案） |

---

## 核心执行链路（施工时时刻牢记）

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

## 两阶段对话交互模式

系统采用**两阶段对话交互**，区分自然语言闲聊/确认与结构化任务执行：

### 阶段一：对话阶段（Dialog Mode）

- **触发**：用户初始输入、补充槽位信息后
- **后端处理**：`process_dialog()` — 自然语言交互，`force_json=False`
- **System Prompt**：`DIALOG_SYSTEM_PROMPT`，强调中文回答、身份是"配药助手"
- **返回**：前端收到 `dialog_reply` 消息，语音播报（TTS）
- **典型场景**：用户问"我要配药"、"帮我查一下库存"、"这个药品是干嘛用的"
- **关键**：此阶段**不**生成 intent_json，仅用于闲聊、查询、补槽澄清。
  - 对话阶段**不阻塞**：LLM 输出自然语言回复后立刻返回，**不串行调用**后台 intent 解析
  - 用户可自由多轮对话，补充槽位信息

### 阶段二：命令阶段（Command Mode）

- **触发**：
  - 用户点击前端的"确认执行"按钮
  - 前端发送 `confirm` 消息类型
- **后端处理**：`resolve_intent_from_dialog()` — 从**完整对话历史**中解析意图，`force_json=True`
  - 把多轮对话历史注入 LLM，提取最终意图
  - 若信息不足：返回反问，用户继续补充
  - 若信息完整：规则引擎校验 → command JSON → 状态机 → TCP 下发 → C++ 执行
- **关键**：**必须**通过规则引擎校验和状态机检查后才能执行

### 前端"确认执行"按钮

- 对话阶段结束后，前端在存在 `pending_intent` 时展示"确认执行"按钮
- 用户确认后，后端才从对话历史中解析意图并执行
- 确认后进入 `PROCESSING` 状态，前端显示加载中
- 若解析失败或信息不足，AI 会反问并返回对话阶段

### 关键边界

1. LLM **在对话阶段输出自然语言**（dialog_reply），**在命令阶段输出 intent_json**（格式见 `shared/intent_schema.json`）
2. **后台 intent 解析改为异步触发**：对话阶段不串行解析，用户点击"确认执行"后才解析
3. **command JSON** 由规则引擎生成，字段值来自数据库，不来自 LLM
4. LLM **不直接输出底层运动控制指令**
5. 前端不直接控制设备
6. 所有执行必须经过规则引擎、状态机和控制白名单约束
7. 天平直连 Jetson，不经过 C++ 控制程序

---

## 核心数据流

1. USB 麦克风采集语音
2. VAD 检测语音起止
3. whisper.cpp 转写文字
4. LLM（llama.cpp server）进行意图识别与槽位完整性判断，输出 `intent_json`
5. 若槽位不足（`is_complete: false`）：TTS 播报 `clarification_question`，等待补充
6. 若槽位完整：规则引擎查药品库补全字段，生成 `command JSON`
7. 状态机确认设备就绪
8. command JSON 通过 TCP 下发给 C++ 后级控制程序
9. 执行期间天平数据持续推送前端，达到目标重量后通知 C++ 停止
10. C++ 回调执行结果，写入日志并反馈到前端

---

## 技术口径

- 主控平台：Jetson Orin NX 16GB + Super Mode
- ASR：whisper.cpp
- LLM：**Qwen3-4B-Instruct-2507-Q4_K_M**（通过 llama.cpp server 部署，接口 `http://localhost:8080/v1`，OpenAI 兼容格式，显存占约 2.5GB）
- TTS：**MeloTTS**（本地服务化运行于 `http://127.0.0.1:8020`，CPU/GPU 自动切换，文本前置规范化）
- 视觉：固定 ROI + QRCodeDetector，必要时加轻量检测模型
- 前端：HTML / Vue 本地网页
- 后端：FastAPI
- 数据存储：SQLite + JSON
- 后级控制通信：**TCP + JSON**（与 C++ 控制程序通信，下发 command JSON，接收回调）
- 天平通信：**MT-SICS over RS422-USB**（梅特勒 WKC204C，直连 Jetson，pyserial 驱动）
- **单位约定：系统全链路质量单位统一为 mg 整数，禁止使用克（g）或浮点克值**

---

## 数据存储架构

本系统采用“**SQLite + JSON 文件**”的混合存储架构。

- **SQLite**：用于保存药品、配方、工位、任务、执行记录、报警记录等结构清晰、需要查询统计和关联分析的业务数据
- **JSON 文件**：用于保存系统配置、标定参数、模型配置、规则模板以及 LLM 原始输出快照等层级较深、人工可读性要求较高的数据

其中，SQLite 负责业务数据的规范化存储与可追溯查询，JSON 负责配置类和快照类数据的灵活管理与人工维护。高频实时控制状态原则上以内存态管理，必要时再按规则落库或落盘。

---

## 绝对约束

### 业务约束
1. 信息不足必须先反问，不得直接执行
2. LLM 不得直接驱动机械动作
3. 未通过规则校验的任务一律拒绝执行
4. 关键动作支持人工确认
5. 日志、异常和执行反馈必须完整记录

### 代码约束
6. 禁止 `as any` / `@ts-ignore`
7. 禁止空 catch 块
8. 所有外部输入必须经过 Schema 校验
9. 配置路径、模型路径、数据库路径必须从配置读取

---

## 环境变量清单（`.env` 模板）

```env
# ASR (whisper-server HTTP 服务)
WHISPER_SERVER_URL=http://127.0.0.1:8081
WHISPER_CPP_MODEL_PATH=models/whisper/ggml-base.bin
WHISPER_LANGUAGE=zh
WHISPER_VAD_THRESHOLD=0.5
AUDIO_SAMPLE_RATE=16000
AUDIO_CHUNK_SIZE_MS=100
AUDIO_MAX_BUFFER_MS=30000

# LLM (llama.cpp server)
LLM_BASE_URL=http://localhost:8080/v1
LLM_MODEL_PATH=models/Qwen/Qwen3-4B-Instruct-2507-Q4_K_M.gguf
LLM_CONTEXT_LENGTH=4096
LLM_MAX_TOKENS=1024
LLM_TEMPERATURE=0.1
LLM_GP_LAYERS=99
LLM_THREADS=6
TTS_PROVIDER=melotts
TTS_BASE_URL=http://localhost:8020
TTS_TIMEOUT_SEC=60
TTS_PLAY_DEFAULT=true
SQLITE_DB_PATH=data/app.db
RULES_CONFIG_PATH=config/rules.json
CONTROL_ADAPTER_HOST=localhost
CONTROL_ADAPTER_PORT=9000
BALANCE_SERIAL_PORT=/dev/ttyUSB0
BALANCE_BAUD_RATE=9600
AUDIO_DEVICE_INDEX=0
CAMERA_DEVICE_INDEX=0
ENV=development
LOG_LEVEL=INFO
```

### 代理配置（重要）

若系统设置了 HTTP 代理（如 `http_proxy=http://127.0.0.1:7890`），本地服务通信会被代理拦截导致连接失败。**必须在 `~/.bashrc` 中配置 `no_proxy` 绕过本地服务：**

```bash
export no_proxy="localhost,127.0.0.1,192.168.10.*"
```

配置后执行 `source ~/.bashrc` 或重新打开终端生效。`start-all.sh` 脚本已内置 `NO_PROXY` 变量，但用户终端环境变量优先级更高。

---

## 接口规范速查

### 前端 ↔ 后端
- `HTTP/REST + WebSocket`
- WebSocket 实时推送：天平读数、任务状态、语音转写、设备状态
- WebSocket 音频消息：
  - 前端发送：二进制 PCM 音频帧 + `audio.commit`
  - 兼容旧协议：`audio_chunk`（base64 PCM）、`audio_end`
  - 后端返回：`asr.final`（转写文本）、`state.update`（录音/识别/思考状态）
  - 语音输入前必须确认 WebSocket 已连接；若连接断开，前端立即提示并放弃本次录音，避免“看起来在录音但实际未发送”

### 后端 ↔ whisper-server（ASR HTTP 服务）
- 地址：`http://127.0.0.1:8081`
- 接口：`POST /inference`（上传 WAV 音频，返回转写结果）
- 启动脚本：`scripts/start-whisper-server.sh`

### 后端 ↔ C++ 后级控制程序（TCP）
- `POST http://{CONTROL_ADAPTER_HOST}:{CONTROL_ADAPTER_PORT}/api/command`（下发 command JSON）
- `GET  http://{CONTROL_ADAPTER_HOST}:{CONTROL_ADAPTER_PORT}/api/status`（查询设备状态）
- `POST /api/tasks/callback`（C++ 回调 AI 层的执行结果）

### 后端 ↔ 天平（RS422-USB 串口）
- 串口设备：`BALANCE_SERIAL_PORT`（默认 `/dev/ttyUSB0`）
- 协议：MT-SICS ASCII，常用命令：`S`（稳定重量）、`SI`（即时重量）、`Z`（归零）
- 数据方向：后端单向读取 → 转换为 mg 整数 → WebSocket 推前端 / 执行监控

### 设备侧（C++ 控制程序负责）
- 电机驱动器：`RS485 + Modbus RTU`（或按实际驱动器协议）
- 其他现场设备：`CAN / 串口 / TCP`

---

## 常见施工场景快速定位

| 我要做什么 | 去哪个文件 |
|-----------|-----------|
| 修改 ASR 引擎或词表 | `backend/app/services/ai/stt.py` |
| 修改 LLM 意图理解 / prompt 逻辑 | `backend/app/services/dialog/intent.py` |
| 修改 LLM 输出格式约束 | `shared/intent_schema.json` |
| 修改下发给 C++ 的指令格式 | `shared/command_schema.json` + `docs/command_protocol.md` |
| 修改规则引擎或状态机 | `backend/app/services/dialog/` |
| 修改天平驱动（MT-SICS 读取/解析） | `backend/app/services/device/balance_mtsics.py` |
| 增加视觉检测逻辑 | `backend/app/services/vision/` |
| 修改 C++ 控制程序通信协议适配 | `backend/app/services/device/` + `docs/command_protocol.md` |
| 修改前端触摸屏交互 | `frontend/src/` |
| 修改数据库表结构或 Pydantic 模型 | `backend/app/models/` / `backend/app/schemas/` |
| 查看药品字段定义 | `shared/command_schema.json` → `definitions.reagent_full` |

---

## 启动顺序

### 一键启动（推荐）

```bash
# 开发模式：启动全部（含 mock-qt + Vite dev server）
./scripts/start-all.sh

# 生产模式：跳过 mock-qt 和 frontend dev server
./scripts/start-all.sh --prod

# 停止所有服务
./scripts/stop-all.sh

# 检查服务状态
./scripts/status.sh
```

### 单服务控制

```bash
# LLM 服务
./llama_server.sh start|stop|restart|status|logs

# ASR 服务
./scripts/start-whisper-server.sh start|stop|restart|status|logs
```

### 手动启动顺序

| 序号 | 服务 | 端口 | 启动命令 | 说明 |
|------|------|------|---------|------|
| 1 | whisper-server | 8081 | `./scripts/start-whisper-server.sh start` | ASR，无依赖 |
| 2 | llama-server   | 8080 | `./llama_server.sh start` | LLM，GPU 加载约 30-60 秒 |
| 3 | MeloTTS        | 8020 | `backend/venv/bin/python melotts-git/melo/tts_server.py --port 8020` | TTS |
| 4 | mock-qt        | 9000 | `mock-qt/venv/bin/python mock-qt/server.py --port 9000` | 后级控制模拟（仅开发）|
| 5 | backend        | 8000 | `backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend` | FastAPI 后端 |
| 6 | frontend       | 5173 | `cd frontend && npx vite --port 5173` | Vue 前端（开发）|

### 注意事项

- **llama-server**：PID 保存在根目录 `.llama_server.pid`，日志在 `logs/llama_server.log`
- **whisper-server**：PID 保存在 `.whisper_server.pid`，需先编译 whisper.cpp
- **mock-qt**：必须使用 `mock-qt/venv/bin/python`（系统 Python 缺少 httpx）
- **backend venv**：必须先运行 `cd backend && python3.11 -m venv venv && pip install -r requirements.txt`
- **日志目录**：`logs/`，命名格式：`{服务名}.log`
- **代理绕过**：`start-all.sh` 自动设置 `no_proxy=localhost,...`；手动启动时若系统设置了 HTTP 代理，须在 `~/.bashrc` 中配置 `no_proxy`

### 服务健康端点

| 服务 | 健康检查 URL |
|------|-------------|
| whisper-server | `http://127.0.0.1:8081/` |
| llama-server   | `http://127.0.0.1:8080/health` |
| MeloTTS        | `http://127.0.0.1:8020/health` |
| mock-qt        | `http://127.0.0.1:9000/api/status` |
| backend        | `http://127.0.0.1:8000/health` |

---

## MCP Server 说明（`mcp-server/`）

### 什么是 MCP Server

MCP（Model Context Protocol）Server 将系统的核心能力封装为标准工具接口，AI 可通过 MCP 协议按需调用，实现自然交互 + 选择性调用的工作流。

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
python3.11 -m venv venv
./venv/bin/pip install -r requirements.txt

# 复制环境变量
cp .env.example .env

# 启动 MCP Server（stdio 模式）
./venv/bin/python server.py
```

### 配置 MCP Client

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

### 扩展新工具

在 `mcp-server/tools/` 下新建 Python 文件，实现 `register(mcp, backend_url)` 函数，使用 `@mcp.tool()` 装饰器定义工具，然后在 `server.py` 中导入并注册即可。
