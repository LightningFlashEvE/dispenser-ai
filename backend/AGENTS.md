# backend/AGENTS.md — 后端施工指南

> 进入后端施工前，**必须先读根目录 AGENTS.md**，再读本文件。

---

## 后端定位

后端运行在 Jetson 主控上，负责：

1. 语音链路：VAD → ASR(whisper.cpp) → ASR guard → Intent Router → AIExtractor patch → DraftManager → Validator → catalog lookup → 结构化确认 → 规则引擎 → command JSON → TTS(MeloTTS)
2. 视觉链路：固定 ROI 检测 → 二维码识别 → 坐标换算
3. 天平驱动：MT-SICS over RS422-USB，读取重量 → mg 整数 → WebSocket 推前端 + 执行监控
4. 控制适配层：proposal / intent 校验（`shared/intent_schema.json`）、规则引擎、状态机、command JSON 生成（`shared/command_schema.json`）、TCP 通信
5. 数据管理：药品（含多语言名称/别名/摩尔质量）、配方、工位、任务、日志、异常
6. 与 C++ 后级控制程序通过 **TCP + JSON** 通信（不是 localhost HTTP，是 TCP）

---

## 技术栈

| 组件 | 说明 |
|------|------|
| Python 3.x | 主语言；JetPack 6.x 默认使用系统 `python3` 创建 venv，不强依赖 `python3.11` 包名 |
| FastAPI | 本地 API 与 WebSocket 服务 |
| Pydantic v2 | 输入输出校验 |
| SQLite + JSON | 本地数据存储 |
| whisper.cpp | 本地离线 ASR |
| llama.cpp server | 本地 LLM 服务；通过 `http://localhost:8080/v1` OpenAI 兼容接口调用；模型 Qwen3-4B-Instruct-2507-Q4_K_M（约 2.5GB 显存）；全层 GPU 推理 |
| MeloTTS (独立服务) | TTS 服务化运行于 `http://127.0.0.1:8020`，独立 venv 隔离，文本前置规范化 |
| OpenCV | 视觉识别与坐标相关处理 |
| pyserial | 天平 MT-SICS 串口通信（RS422-USB） |

---

## 关键边界

1. AIExtractor 只输出字段 patch，不输出 `complete` / `ready_for_review` 的可信判断，不生成最终 intent / command。
2. `chemical_id` 只能来自 catalog lookup 或用户候选选择，AI 不能写入。
3. AI 不能写 `slot_id` / `motor_id` / `pump_id` / `valve_id` / `station_id` 等控制层字段。
4. DraftManager 负责合并 patch、过滤非法字段、持久化 draft、记录 audit events。
5. Validator 负责判断 `missing_slots` / `pending_confirmation_fields` / `READY_FOR_REVIEW`。
6. `command JSON`（格式见 `shared/command_schema.json`）由规则引擎和 adapter 层生成，字段值来自数据库和已确认 catalog 数据。
7. 用户确认 = `self_approved`，但必须先通过规则引擎、状态机、库存和设备状态校验。
8. 规则通过才允许 `build_command()` / `send_command()`；规则失败不下发。
9. 重复确认不能重复生成 proposal 或重复下发 command。
10. 后端天平驱动只负责读数，不直接控制下料电机（下料由 C++ 控制）。
11. 后端不直接进行设备级动作控制（机械臂/电机/IO 联锁均由 C++ 负责）。
12. C++ 后级控制程序负责机械臂、下料电机、IO 联锁与急停逻辑。

---

## 建议目录结构

```
backend/
├── app/
│   ├── api/                        # REST 接口（配方/药品/日志管理、C++ 回调接收）
│   ├── ws/                         # WebSocket（语音交互、天平实时数据推送）
│   ├── core/                       # 配置、日志、异常处理
│   ├── services/
│   │   ├── ai/                     # ASR(whisper.cpp) / LLM(llama.cpp) / TTS(MeloTTS) / VAD
│   │   ├── vision/                 # ROI检测 / QRCodeDetector / 坐标换算
│   │   ├── dialog/                 # 意图解析、槽位管理、规则引擎、状态机
│   │   ├── device/
│   │   │   ├── balance_mtsics.py   # 天平 MT-SICS 驱动（RS422-USB）
│   │   │   └── control_client.py   # C++ 控制程序 TCP 客户端
│   │   └── inventory/              # 药品库、配方库、工位状态管理
│   ├── models/                     # SQLAlchemy ORM 模型
│   └── schemas/                    # Pydantic v2 输入输出 Schema
└── tests/
```

---

## 核心执行链路

系统采用 **draft workflow**，后端负责状态和执行判断：

```
二进制 PCM 音频帧 / 文本输入 / 前端表单
  ↓
audio.commit → whisper-server ASR → asr.final
  ↓
ASR guard（raw_text / normalized_text / confidence / needs_confirmation）
  ↓
Intent Router（普通对话、查询、start_task、update_task、cancel_task、confirm_task）
  ↓
AIExtractor patch（只提取本轮字段，不生成 command，不写 chemical_id）
  ↓
DraftManager merge（session 级 draft，非法字段过滤，审计事件，持久化）
  ↓
Validator（missing_slots / pending_confirmation_fields / READY_FOR_REVIEW）
  ↓
Chemical Catalog lookup（0 候选阻止；多候选等待选择；chemical_id 后端写入）
  ↓
WebSocket 推 draft_update → 前端结构化确认卡片
  ↓
用户确认 → approval_mode=self_approved
  ↓
后端生成 proposal / intent JSON
  ↓
规则引擎 + 状态机 + 库存 + 设备状态校验
  ↓
build_command() → command JSON
  ↓
send_command() → C++ 后级控制程序
  ↓
执行回调 → 日志落库 + WebSocket 推前端

天平（并行常驻）：
pyserial → MT-SICS → mg整数 → WebSocket推前端 + 执行期监控
```

- 普通聊天、库存查询、设备状态查询、配方查询属于只读/对话 route，不进入执行。
- WEIGHING / DISPENSING 等任务必须先形成 draft，再进入结构化确认。
- Formula 查询只读；Formula 选择生成 proposal，用户确认后也必须过规则校验才能执行。
- 前端录音开始前必须先确认 WebSocket 已连接；若连接断开，直接提示并取消本次录音，避免无效音频提交。
- **必须**通过规则引擎和状态机检查后才能执行。

---

## 数据建议

建议至少管理以下数据：

- **药品主数据**：含 `reagent_code`（主键）、`reagent_name_cn`、`reagent_name_en`、`reagent_name_formula`（化学式）、`reagent_aliases`（别名列表，用于模糊匹配）、`cas_number`、`purity_grade`、`molar_weight_g_mol`（操作员预设）、`density_g_cm3`、`station_id`、`stock_mg`、`notes`
- **配方主数据**：含配方名、别名列表、步骤列表（关联药品）
- **工位状态数据**
- **执行任务数据**：含 intent_json 快照、command JSON 快照、回调结果
- **审计日志数据**
- **异常与报警数据**

### 存储架构说明

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

## 配置建议

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
INTENT_SCHEMA_PATH=../shared/intent_schema.json
COMMAND_SCHEMA_PATH=../shared/command_schema.json
CONTROL_ADAPTER_HOST=localhost
CONTROL_ADAPTER_PORT=9000
BALANCE_SERIAL_PORT=/dev/ttyUSB0
BALANCE_BAUD_RATE=9600
```

---

## 关键约束

1. 所有任务必须先过 Schema 校验
2. 所有任务必须先过规则引擎和状态机
3. 日志必须覆盖输入、校验、下发、回调、异常全过程
4. 异常情况下必须支持降级或人工介入
5. **系统全链路质量单位统一为 mg 整数，禁止在任何接口、数据库字段或日志中使用克（g）或浮点克值**
6. 天平通信使用 MT-SICS 协议（非 Modbus），天平驱动层将读数转换为 mg 整数后通过 WebSocket 推前端展示
7. **天平仅用于前端展示**，称重闭环和停止时机由 C++ 控制程序自主决定，AI 层不下发停止指令

## 规则引擎关键规则

### confirmation 校验规则
- **必须有 confirmation**：`dispense` / `aliquot` / `mix` / `formula` / `restock`
- **不需要 confirmation**：`query_stock` / `device_status` / `cancel` / `emergency_stop`
- 开发阶段可通过 `.env` 的 `SKIP_CONFIRMATION=true` 跳过，**生产必须为 false**

### 量程校验
- 天平量程上限从配置读取：`BALANCE_MAX_MASS_MG`，默认 `220000`（220g）
- 规则引擎校验：`target_mass_mg ≤ BALANCE_MAX_MASS_MG`，超出拒绝并 TTS 提示

### aliquot target_vessels 自动分配
- LLM 输出 `target_vessels=null` 时，规则引擎从视觉层获取当前空闲工位列表
- 若空闲工位数 < `portions`，拒绝并 TTS 提示"当前空闲容器不足，需要 N 个，当前仅有 M 个"
- 若足够，按视觉层返回顺序自动填充 `target_vessels`

### 默认容差规则
- 用户未指定 `tolerance_mg` 时：`max(DEFAULT_TOLERANCE_MG, target_mass_mg * DEFAULT_TOLERANCE_PCT / 100)`
- 默认值从配置读取：`DEFAULT_TOLERANCE_MG=10`，`DEFAULT_TOLERANCE_PCT=2.0`

### 对话状态（内存维护 · 任务级清空策略）

**当前策略：任务级清空**
每次任务完成/取消/出错后立即清空对话历史，补槽期间保留当次对话，上限 `DIALOG_MAX_ROUNDS` 轮。

选择原因：配药操作是单任务一问一答模式，用户不会跨任务引用历史，实现最简单。

**实现要点：**
- 一个 WebSocket 连接 = 一个 `Session` 实例（`app/services/dialog/session.py`），完全内存态。
- WebSocket 会话标识通过 query 参数 `session_id` 传入，例如 `/ws/voice?session_id=...`，用于恢复历史对话。
- 每个 Session 内含 `dialog_history`（自然语言）与 `intent_history`（结构化 JSON）两条独立列表，分别注入给 LLM 的 dialog / intent 两个调用，避免格式互相污染。
- 单次任务最大补槽轮数：`DIALOG_MAX_ROUNDS=8`，超出后重置并 TTS 提示"对话轮数过多，已重置"。
- 任务完成/取消/出错后立即调用 `session.reset()` 清空。

### WebSocket 语音消息（当前协议）

- 前端发送：
  - `[binary frame]`：PCM Int16 音频帧
  - `audio.commit`：本轮录音结束，触发 ASR
  - `chat.user_text`：文本输入
  - `barge_in`：打断当前 TTS 播放
- 后端返回：
  - `state.update`：`listening / recognizing / thinking / speaking / awaiting_confirmation / idle`
  - `asr.final`：ASR 最终转写
  - `chat.delta` / `chat.done`：AI 流式回复
  - `pending_intent` / `pending_cleared`
  - `tts.chunk` / `tts.done` / `tts_end`
- 中文输出约束：
  - `asr.final` 必须统一输出简体中文，再进入对话历史和后续 LLM 解析，避免 whisper 根据口音输出繁体或繁简混合文本
- 兼容旧协议：
  - `audio_chunk` / `audio_end` / `transcript`
  - 旧版 base64 音频块必须做异常保护，坏包只返回错误，不允许打断整个 WebSocket 会话

### Draft / Pending 确认机制

- 用户描述任务时，dispatcher 只创建或更新 draft，通过 WebSocket 推 `draft_update`。
- `READY_FOR_REVIEW` 只代表表单字段、ASR guard、catalog confirmation 已满足，可以展示确认卡片；不代表任务一定可执行。
- 前端确认卡片只在 `ready_for_review=true` 时启用确认按钮。
- 用户点击或说精确关键词（`确认执行 / 确认 / 开始执行 / 执行`）触发 `confirm` 消息。
- 用户确认后，后端生成 proposal / intent，并标记 `approval_mode=self_approved`、`approved_by=current_operator`、`approved_at=...`。
- 规则校验通过后才调用 `build_command()` / `send_command()`；规则失败返回原因并阻止下发。
- `PENDING_INTENT_TTL_SEC` 秒后自动过期（默认 60s），避免误执行。
- 不再用 `好的 / 是的 / 可以` 等宽泛关键词触发执行。
- 重复确认必须幂等，不能重复创建 proposal 或重复下发 command。

## 天平通信说明（梅特勒 WKC204C）

- 接口：RS422，通过 RS422-USB 工业隔离转换器接入 Jetson
- 协议：MT-SICS ASCII 串口命令集
- 驱动库：`pyserial`
- 关键命令：`S`（稳定重量）、`SI`（即时重量）、`Z`（归零）、`ZI`（立即归零）
- 响应解析：提取数值（单位 g），× 1000 取整后以 mg 整数推送 WebSocket
- **职责**：数据只流向前端展示，不用于控制决策
- 驱动位置：`backend/app/services/device/balance_mtsics.py`（待实现）
