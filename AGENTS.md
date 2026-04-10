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
| `shared/` | Schema 契约文件（intent_schema.json + command_schema.json） | 见下方 Schema 说明 |
| `mock-qt/` | 模拟 C++ 后级控制程序，用于开发联调 | [mock-qt/AGENTS.md](mock-qt/AGENTS.md) |
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

---

## 核心执行链路（施工时时刻牢记）

```
语音/界面输入
  ↓
ASR（whisper.cpp）/ 表单输入
  ↓
LLM（Ollama）→ intent_json（见 shared/intent_schema.json）
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

### 关键边界

1. LLM **只输出 intent_json**（语义层，格式见 `shared/intent_schema.json`）
2. **command JSON** 由规则引擎生成，字段值来自数据库，不来自 LLM
3. LLM **不直接输出底层运动控制指令**
4. 前端不直接控制设备
5. 所有执行必须经过规则引擎、状态机和控制白名单约束
6. 天平直连 Jetson，不经过 C++ 控制程序

---

## 核心数据流

1. USB 麦克风采集语音
2. VAD 检测语音起止
3. whisper.cpp 转写文字
4. LLM（Ollama）进行意图识别与槽位完整性判断，输出 `intent_json`
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
- LLM：Gemma 4 E4B、Qwen2.5-3B/7B、Phi-3 Mini 候选（通过 **Ollama** 部署，`OLLAMA_KEEP_ALIVE=0`，接口 `http://localhost:11434/v1`）
- TTS：MeloTTS
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
WHISPER_CPP_MODEL_PATH=models/whisper/ggml-base.bin
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_KEEP_ALIVE=0
MELOTTS_MODEL_PATH=models/melotts
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

---

## 接口规范速查

### 前端 ↔ 后端
- `HTTP/REST + WebSocket`
- WebSocket 实时推送：天平读数、任务状态、语音转写、设备状态

### 后端 ↔ C++ 后级控制程序（TCP）
- `POST http://{CONTROL_ADAPTER_HOST}:{CONTROL_ADAPTER_PORT}/api/command`（下发 command JSON）
- `GET  http://{CONTROL_ADAPTER_HOST}:{CONTROL_ADAPTER_PORT}/api/status`（查询设备状态）
- `POST /api/device/callback`（C++ 回调 AI 层的执行结果）

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
