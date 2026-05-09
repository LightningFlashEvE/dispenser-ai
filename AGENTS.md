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
| `mcp-server/` | 可选 MCP Server，将系统能力封装为外部 AI Client 可调用的工具；不参与主流程，不随 `start-dev.sh` 启动 | 见下方 MCP Server 说明 |
| `shared/` | Schema 契约文件（intent_schema.json + command_schema.json） | 见下方 Schema 说明 |
| `mock-qt/` | 模拟 C++ 后级控制程序，用于开发联调 | [mock-qt/AGENTS.md](mock-qt/AGENTS.md) |
| `libs/` | 可选本机二进制资产目录（llama.cpp / whisper.cpp 编译产物 `.so`） | 不进 Git；目标机优先本地编译，必要时从 Release/对象存储下载 |
| `docs/` | 架构/协议/硬件文档 | 见下方文档索引 |

---

## Schema 文件说明（`shared/`）

| 文件 | 用途 | 版本 |
|------|------|------|
| `shared/intent_schema.json` | 后端在用户确认 draft 后生成的正式 proposal / intent JSON，规则引擎校验用 | v1.0 |
| `shared/command_schema.json` | 下发给 C++ 控制程序的执行指令格式，双方接口契约 | v2.1 |

**两个 Schema 的区别：**
- `intent_schema`：语义层，由后端基于已确认 draft / proposal 生成；AI 只能提供 patch，不能直接生成最终 intent
- `command_schema`：执行层，字段来自数据库、catalog lookup、规则引擎和状态机，所有字段必须合法且通过校验

---

## 文档索引

| 文档 | 用途 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 系统分层、边界、执行链路、天平数据流说明 |
| [docs/command_protocol.md](docs/command_protocol.md) | intent_json 与 command JSON 协议完整说明 |
| [docs/hardware_setup.md](docs/hardware_setup.md) | 硬件选型（含天平 WKC204C）、部署、运维与排障 |
| [docs/llm_prompt_design.md](docs/llm_prompt_design.md) | LLM system prompt 模板、工位快照注入、对话历史格式、典型场景示例、后端实现要点 |
| [docs/upgrade-v0.2.md](docs/upgrade-v0.2.md) | v0.2 重构升级手册（破坏性变更说明、Jetson 升级步骤、验收清单、回滚方案） |
| [docs/assets.md](docs/assets.md) | 大模型、编译产物、venv、数据库等不进 Git 资产的分发与恢复说明 |

---

## 核心执行链路（施工时时刻牢记）

```
用户输入（语音 / 文本 / 前端表单）
  ↓
Intent Router（分流：普通对话、查询、开始/更新/取消/确认任务）
  ↓
AIExtractor patch（AI 只提取本轮字段 patch）
  ↓
DraftManager merge（后端合并 session 级 draft，记录审计事件）
  ↓
Validator（后端判断 missing_slots / ready_for_review）
  ↓
ASR guard（保留 raw_text / normalized_text / confidence，低置信关键字段先确认）
  ↓
Chemical Catalog lookup（chemical_id 只能来自 catalog lookup 或用户候选选择）
  ↓
前端结构化确认卡片（任务字段、catalog 匹配、ASR 提示、确认/修改/取消）
  ↓
用户确认 = self_approved（本机操作员确认即授权）
  ↓
后端规则校验（库存、单位、容器、设备状态、配方步骤等硬门槛）
  ↓
build_command（生成 shared/command_schema.json）
  ↓
send_command（TCP/HTTP 适配层下发最终 command JSON）
  ↓
C++ 控制层（只执行后端签发的 command JSON）
  ↓
执行反馈 → 页面与语音反馈

天平数据流（并行常驻，仅展示）：
天平 WKC204C → RS422-USB → 后端 MT-SICS 驱动 → mg 整数 → WebSocket → 前端实时展示
（称重闭环由 C++ 自主决定，AI 层不干涉）
```

## 通信与实时数据边界

后续施工必须按数据性质选择通道，避免把查询、采样和执行语义混在 WebSocket 里：

- **称重实时曲线**：WebSocket 可高频推送，但只用于前端显示；前端必须分离采集频率、数字显示频率和图表渲染频率，控制层判断不依赖前端曲线。
- **Dashboard 系统资源**：后端后台 sampler 采集并缓存，HTTP 接口只读取 cache；不得在 `async` API 里直接执行阻塞采样、`subprocess.run()` 或长 `psutil` 调用来阻塞 event loop。
- **任务确认 / 执行**：后端状态机 + 规则校验 + `command_id` 是唯一执行链路；WebSocket 只展示 draft、规则校验、command 下发和执行进度，不承担执行授权之外的安全保证。
- **历史任务 / 日志 / 审计**：HTTP 分页查询；WebSocket 最多推新增或状态变更通知，不传全量历史。
- **库存 / 配方 / 药品库**：HTTP 查询和修改；WebSocket 只推变更通知或提示前端刷新。
- **急停 / 安全联锁**：控制层硬件优先，后端只显示状态和记录事件；不得依赖前端 WebSocket 作为安全链路。

## Draft 对话任务模式

系统采用 **draft workflow**，把“语言理解”和“任务完整性 / 执行判断”分开：

### 对话与查询

- 普通聊天、库存查询、设备状态查询、配方查询可以直接返回自然语言或只读结果。
- 查询类结果不能被当成执行授权；例如 `query_formula` 只展示配方，`select_formula` 才进入 proposal。
- 已有 active draft 时，用户后续输入默认更新当前 draft；第一版同一 session 同时只允许一个 active draft。

### 任务草稿收集

- Intent Router 负责保守分流：`start_task` / `update_task` / `cancel_task` / `confirm_task` / 查询类 route。
- AIExtractor 只输出本轮字段 patch，不输出最终 command，不判断 `complete` / `ready_for_review`。
- DraftManager 负责合并 patch、过滤非法字段、持久化 draft、记录 audit events。
- Validator 负责判断 `missing_slots`、`pending_confirmation_fields` 和是否进入 `READY_FOR_REVIEW`。
- ASR guard 对语音输入保留 `raw_text`、`normalized_text`、`confidence`、`needs_confirmation`；低置信关键字段必须先确认。
- Chemical Catalog lookup 负责把用户文本匹配到真实化学品；`chemical_id` 只能来自 catalog lookup 或用户选择候选。

### 用户确认与执行

- 前端在 `READY_FOR_REVIEW` 时展示结构化确认卡片，而不是只依赖 AI 自然语言。
- 用户确认卡片 = `self_approved`，表示当前本机操作员授权执行。
- 用户确认不能绕过规则校验；后端必须先跑规则引擎 / 状态机 / 库存 / 设备状态检查。
- 规则通过后才允许 `build_command()` 和 `send_command()`。
- 规则失败必须返回失败原因，不下发 command。
- 重复确认不能重复生成 proposal 或重复下发 command。

### AI 绝对边界

1. AI 只能提取 patch。
2. AI 不能判断任务完整性。
3. AI 不能生成 command JSON。
4. AI 不能写 `chemical_id`。
5. AI 不能写 `slot_id` / `motor_id` / `pump_id` / `valve_id` / `station_id` 等控制层字段。
6. `chemical_id` 只能来自 catalog lookup 或用户候选选择。
7. command JSON 由后端规则引擎和 adapter 层生成，字段值来自已校验的后端数据。
8. 前端不直接控制设备。
9. 天平直连 Jetson，不经过 C++ 控制程序。

---

## 核心数据流

1. USB 麦克风采集语音
2. VAD 检测语音起止
3. whisper.cpp 转写文字
4. Intent Router 判断输入属于查询、普通对话、开始任务、更新任务、取消任务或确认任务
5. AIExtractor 只提取字段 patch；后端 DraftManager 合并到当前 draft
6. Validator 判断缺失字段；ASR guard 与 catalog lookup 判断是否需要人工确认关键字段 / 候选
7. draft 完整后前端展示结构化确认卡片
8. 用户确认后，后端生成 proposal / intent JSON，并标记 `approval_mode=self_approved`
9. 规则引擎、状态机、库存和设备状态校验通过后，生成 command JSON
10. command JSON 通过 TCP/HTTP 适配层下发给 C++ 后级控制程序
11. 执行期间天平数据持续推送前端；称重闭环和停止时机由 C++ 控制程序自主决定
12. C++ 回调执行结果，写入日志并反馈到前端

---

## 技术口径

- 主控平台：Jetson Orin NX 16GB + Super Mode
- ASR：whisper.cpp
- LLM：**Qwen3-4B-Instruct-2507-Q4_K_M**（通过 llama.cpp server 部署，接口 `http://localhost:8080/v1`，OpenAI 兼容格式，显存占约 2.5GB）
- TTS：**MeloTTS**（本地服务化运行于 `http://127.0.0.1:8020`，CPU/GPU 自动切换，文本前置规范化）
- 视觉：固定 ROI + QRCodeDetector，必要时加轻量检测模型
- 前端：Vue 3 + Vite + TypeScript + Pinia；ECharts 为主图表库；Tailwind + shadcn-vue 为主视觉；Element Plus 仅用于复杂表格、表单、弹窗、分页；lucide-vue-next 为主图标库
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

### SQLite schema 变更规则

- SQLite schema 变更必须写幂等 migration，不能只依赖 `Base.metadata.create_all()`。
- `ADD COLUMN` 前必须检查列是否存在。
- 不做破坏性迁移：不得静默删除表、删除列或清空业务数据。
- 开发环境需要重置数据库时，先备份 `data/*.db`，再执行清理。

---

## 绝对约束

### 业务约束
1. 信息不足必须先反问，不得直接执行
2. LLM 不得直接驱动机械动作
3. 未通过规则校验的任务一律拒绝执行
4. 用户确认任务 = 本机自审批，但不能绕过后端规则校验
5. 规则通过才 `build_command` / `send_command`；规则失败不下发
6. 重复确认不能重复下发
7. 日志、异常和执行反馈必须完整记录

### 代码约束
6. 禁止 `as any` / `@ts-ignore`
7. 禁止空 catch 块
8. 所有外部输入必须经过 Schema 校验
9. 配置路径、模型路径、数据库路径必须从配置读取
10. 不得随意引入新的 UI / 图表 / 状态管理库

### 提交前检查命令

```bash
python -m pytest backend/tests/test_formula_selection_flow.py backend/tests/test_task_draft_flow.py backend/tests/test_task_draft_ws.py backend/tests/test_smoke.py backend/tests/test_asr_normalizer.py
npm run typecheck
npm run lint
npm run build
git diff --check
```

---

## 环境变量清单（`.env` 模板）

```env
# ASR (whisper-server HTTP 服务)
WHISPER_SERVER_URL=http://127.0.0.1:8081
WHISPER_CPP_MODEL_PATH=models/whisper/ggml-small.bin
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

配置后执行 `source ~/.bashrc` 或重新打开终端生效。`start-dev.sh` 脚本已内置 `NO_PROXY` 变量，但用户终端环境变量优先级更高。

---

## 接口规范速查

### 前端 ↔ 后端
- `HTTP/REST + WebSocket`
- WebSocket 实时推送：天平读数、语音转写、draft/task 状态变更、command 进度通知
- HTTP/REST 查询和修改：系统资源 cache、历史任务、日志审计、库存、配方、药品库、设备状态快照
- 系统资源接口必须读取后台 sampler cache，不能在请求处理中阻塞 event loop
- WebSocket 音频消息：
  - 前端发送：二进制 PCM 音频帧 + `audio.commit`
  - 兼容旧协议：`audio_chunk`（base64 PCM）、`audio_end`
  - 后端返回：`asr.final`（转写文本）、`state.update`（录音/识别/思考状态）
  - 语音输入前必须确认 WebSocket 已连接；若连接断开，前端立即提示并放弃本次录音，避免“看起来在录音但实际未发送”

### 后端 ↔ whisper-server（ASR HTTP 服务）
- 地址：`http://127.0.0.1:8081`
- 接口：`POST /inference`（上传 WAV 音频，返回转写结果）
- 启动方式：随 `scripts/start-dev.sh` / `scripts/start-prod.sh` 一起启动

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
# Jetson Orin NX 首次部署：安装系统依赖、创建 venv、安装前端依赖、配置 nginx 生产入口
./scripts/setup-nx.sh

# 编译/安装不进 Git 的外部运行时：llama.cpp、whisper.cpp、MeloTTS
./scripts/setup-runtime.sh

# 下载外部模型资产；Qwen 默认使用稳定 Hugging Face resolve/main 地址，
# Hugging Face 不通时可用 QWEN_GGUF_URL 临时覆盖
# export QWEN_GGUF_URL="<Qwen3-4B-Instruct-2507-Q4_K_M.gguf 下载地址>"
DOWNLOAD_WHISPER_SMALL=1 ./scripts/download-models.sh
```

```bash
# 开发模式：启动主系统服务（含 mock-qt + Vite dev server；不启动 mcp-server）
./scripts/start-dev.sh

# 生产模式：跳过 mock-qt 和 frontend dev server
./scripts/start-prod.sh

# 停止所有服务
./scripts/stop-all.sh
```

### 单服务控制

```bash
# LLM 服务仍保留独立控制脚本，便于查看模型加载日志或单独重启
./llama_server.sh start|stop|restart|status|logs
```

### 手动启动顺序

| 序号 | 服务 | 端口 | 启动命令 | 说明 |
|------|------|------|---------|------|
| 1 | whisper-server | 8081 | `./scripts/start-dev.sh` / `./scripts/start-prod.sh` 内部启动 | ASR，无依赖 |
| 2 | llama-server   | 8080 | `./llama_server.sh start` | LLM，GPU 加载约 30-60 秒 |
| 3 | MeloTTS        | 8020 | `melotts-git/venv/bin/python melotts-git/melo/tts_server.py --port 8020` | TTS |
| 4 | mock-qt        | 9000 | `mock-qt/venv/bin/python mock-qt/server.py --port 9000` | 后级控制模拟（仅开发）|
| 5 | backend        | 8000 | `backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend` | FastAPI 后端 |
| 6 | frontend       | 5173 | `cd frontend && USE_HTTPS=true SSL_CERT_PATH=../.certs/vite-dev.crt SSL_KEY_PATH=../.certs/vite-dev.key npx vite --host 0.0.0.0 --port 5173` | Vue 前端（开发，局域网麦克风需 HTTPS）|

### 注意事项

- **llama-server**：PID 保存在根目录 `.llama_server.pid`，日志在 `logs/llama_server.log`
- **llama.cpp 编译**：Jetson Orin NX 使用 `cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=87 -DCMAKE_BUILD_TYPE=Release && cmake --build build --target llama-server -j$(nproc)`
- **whisper-server**：PID 保存在 `.whisper_server.pid`，需先编译 whisper.cpp；Jetson Orin NX 使用 `DGGML_CUDA=ON` 与 `CMAKE_CUDA_ARCHITECTURES=87`
- **mock-qt**：必须使用 `mock-qt/venv/bin/python`（系统 Python 缺少 httpx）
- **backend venv**：优先运行 `./scripts/setup-nx.sh`；手动安装时使用 `cd backend && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt`
- **生产前端**：`./scripts/setup-nx.sh` 会安装并配置 nginx、自签名 HTTPS 证书和 `frontend/dist/` 静态站点；生产入口为 `https://<jetson-ip>/#/dashboard`，`./scripts/start-prod.sh` 只负责构建 dist 并启动/reload nginx。
- **前端麦克风**：`localhost` 可用 HTTP；手机/触摸屏/其他电脑通过局域网 IP 访问时必须使用 HTTPS，否则浏览器会隐藏 `navigator.mediaDevices` 并禁止麦克风。`./scripts/start-dev.sh` 会自动生成 `.certs/vite-dev.crt` / `.certs/vite-dev.key` 并以 HTTPS 启动 Vite。
- **模型与编译产物**：`models/`、`libs/`、`llama.cpp/`、`whisper.cpp/`、`melotts-git/` 不提交 Git；外部运行时用 `./scripts/setup-runtime.sh` 恢复，模型用 `./scripts/download-models.sh` 恢复
- **日志目录**：`logs/`，命名格式：`{服务名}.log`
- **代理绕过**：`start-dev.sh` 自动设置 `no_proxy=localhost,...`；手动启动时若系统设置了 HTTP 代理，须在 `~/.bashrc` 中配置 `no_proxy`

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

MCP（Model Context Protocol）Server 将系统的核心能力封装为标准工具接口，供 Claude Desktop、Cursor、opencode 等外部 AI Client 按需调用。

注意：`mcp-server/` 是可选外部工具接口，不参与当前前端/语音/后端 draft 主流程，`./scripts/start-dev.sh` 不会启动它；需要外部 MCP Client 时按下方步骤手动启动。

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
AI: "找到氯化钠了，在 3 号工位，库存 50g。请在结构化确认卡片中确认。"
用户: "确认"
后端: 基于已确认 draft / proposal 生成 intent JSON，并标记 self_approved
后端: 调用 build_command(intent_json) → 生成 command JSON
后端: 调用 send_command(command_json) → 下发到控制层
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
