# backend/AGENTS.md — 后端施工指南

> 进入后端施工前，**必须先读根目录 AGENTS.md**，再读本文件。

---

## 后端定位

后端运行在 Jetson 主控上，负责：

1. 语音链路：VAD → ASR(whisper.cpp) → LLM(Ollama) → intent_json → 规则引擎 → command JSON → TTS(MeloTTS)
2. 视觉链路：固定 ROI 检测 → 二维码识别 → 坐标换算
3. 天平驱动：MT-SICS over RS422-USB，读取重量 → mg 整数 → WebSocket 推前端 + 执行监控
4. 控制适配层：intent_json 校验（`shared/intent_schema.json`）、规则引擎、状态机、command JSON 生成（`shared/command_schema.json`）、TCP 通信
5. 数据管理：药品（含多语言名称/别名/摩尔质量）、配方、工位、任务、日志、异常
6. 与 C++ 后级控制程序通过 **TCP + JSON** 通信（不是 localhost HTTP，是 TCP）

---

## 技术栈

| 组件 | 说明 |
|------|------|
| Python 3.11+ | 主语言 |
| FastAPI | 本地 API 与 WebSocket 服务 |
| Pydantic v2 | 输入输出校验 |
| SQLite + JSON | 本地数据存储 |
| whisper.cpp | 本地离线 ASR |
| 本地 LLM（Ollama） | 任务级 JSON 生成；通过 `http://localhost:11434/v1` OpenAI 兼容接口调用；配置 `OLLAMA_KEEP_ALIVE=0` 推理后立即释放 GPU |
| MeloTTS | 本地离线 TTS |
| OpenCV | 视觉识别与坐标相关处理 |
| pyserial | 天平 MT-SICS 串口通信（RS422-USB） |

---

## 关键边界

1. LLM 只输出 `intent_json`（格式见 `shared/intent_schema.json`），不输出 command JSON
2. `command JSON`（格式见 `shared/command_schema.json`）由规则引擎生成，字段值来自数据库
3. 后端天平驱动只负责读数，不直接控制下料电机（下料由 C++ 控制）
4. 后端不直接进行设备级动作控制（机械臂/电机/IO 联锁均由 C++ 负责）
5. C++ 后级控制程序负责机械臂、下料电机、IO 联锁与急停逻辑

---

## 建议目录结构

```
backend/
├── app/
│   ├── api/                        # REST 接口（配方/药品/日志管理、C++ 回调接收）
│   ├── ws/                         # WebSocket（语音交互、天平实时数据推送）
│   ├── core/                       # 配置、日志、异常处理
│   ├── services/
│   │   ├── ai/                     # ASR(whisper.cpp) / LLM(Ollama) / TTS(MeloTTS) / VAD
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

```
ASR（whisper.cpp）/ 表单输入
  ↓
LLM（Ollama）→ intent_json（shared/intent_schema.json）
  ↓
规则引擎：校验 intent_json + 查药品库 → command JSON（shared/command_schema.json）
  ↓
状态机：确认设备就绪
  ↓
TCP 下发 command JSON → C++ 后级控制程序
  ↓
执行回调（TCP）→ 日志落库 + WebSocket 推前端

天平（并行常驻）：
pyserial → MT-SICS → mg整数 → WebSocket推前端 + 执行期监控
```

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

---

## 配置建议

```env
WHISPER_CPP_MODEL_PATH=models/whisper/ggml-base.bin
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_KEEP_ALIVE=0
MELOTTS_MODEL_PATH=models/melotts
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

### 对话状态（内存模式 · 任务级清空策略）

**当前策略：任务级清空（方案A）**
每次任务完成/取消/出错后立即清空对话历史，补槽期间保留当次对话，上限 `DIALOG_MAX_ROUNDS` 轮。

选择原因：配药操作是单任务一问一答模式，用户不会跨任务引用历史，实现最简单。

**如后期需要改策略，备选方案：**
- 方案B：固定最近 N 轮滚动（不管任务边界，始终保留最近 N 轮）
- 方案C：Token 预算（累计超过阈值时删最早轮次，最精确但需引入 tokenizer）

**实现要点：**
- 对话历史仅在内存中维护（`dict[session_id, list[Message]]`），进程重启后对话重置
- 单次任务最大补槽轮数：`DIALOG_MAX_ROUNDS=8`，超出后重置并 TTS 提示"请重新描述您的操作"
- 任务完成/取消/出错后立即清空当前 session 的对话历史

## 天平通信说明（梅特勒 WKC204C）

- 接口：RS422，通过 RS422-USB 工业隔离转换器接入 Jetson
- 协议：MT-SICS ASCII 串口命令集
- 驱动库：`pyserial`
- 关键命令：`S`（稳定重量）、`SI`（即时重量）、`Z`（归零）、`ZI`（立即归零）
- 响应解析：提取数值（单位 g），× 1000 取整后以 mg 整数推送 WebSocket
- **职责**：数据只流向前端展示，不用于控制决策
- 驱动位置：`backend/app/services/device/balance_mtsics.py`（待实现）
