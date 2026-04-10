# 指令协议文档 v2.3

> **适用范围**：AI交互层（Python/FastAPI）→ 后级控制程序（C++）
> **协议性质**：本文档是双方的接口契约，任何字段修改须双方确认并升级版本号
> **机器可读 Schema**：
> - 执行指令格式：`shared/command_schema.json`（v2.1，下发给C++控制层）
> - LLM意图格式：`shared/intent_schema.json`（v1.0，AI层内部流转）

> **边界说明**：LLM 仅生成意图 JSON（intent_json，见 `intent_schema.json`），不直接生成底层运动控制指令。真正下发给C++控制程序的结构化指令（command，见 `command_schema.json`），必须先经过规则引擎校验、状态机检查和协议适配后生成。

> **单位约定**：系统全链路（intent_json、command、数据库、回调、日志）统一使用 **mg（毫克）整数** 表示所有质量值。禁止在任何接口或数据结构中使用克（g）或浮点克值。

> **天平数据流**：天平（梅特勒 WKC204C）通过 **RS422-USB** 直接连接 Jetson，由 AI 层后端（Python）通过 MT-SICS 协议读取原始重量数据，转换为 mg 整数后实时通过 WebSocket 推送前端展示。称重闭环（何时停止下料）由 **C++ 控制程序自主决定**，AI 层不下发停止指令。

---

## 0. 意图与执行分离的两层设计

本系统采用**意图层与执行层分离**的两阶段设计，核心原则：

```
LLM → intent_json（意图对象，shared/intent_schema.json）
           ↓
规则引擎 + 状态机 + 设备状态 → command JSON（执行指令，shared/command_schema.json）
           ↓
C++ 后级控制程序（自主决定动作序列和称重闭环）
```

### 0.1 intent_json（意图对象）

intent_json 是 LLM 理解用户意图后输出的结构化描述，属于**语义层**表达。完整格式定义见 `shared/intent_schema.json`。

- **来源**：LLM（自然语言理解 + 槽位补全）
- **内容**：意图类型、试剂模糊提取、参数槽位（允许为 null 表示用户未提供）、槽位完整性标志、反问文本
- **约束**：LLM 不保证药品存在性、工位合法性、摩尔质量正确性等，这些必须由规则引擎查库校验
- **示例（信息完整）**：

```json
{
  "schema_version": "1.0",
  "intent_id": "intent_20260409_001",
  "intent_type": "dispense_powder",
  "timestamp": "2026-04-09T15:30:45+08:00",
  "is_complete": true,
  "missing_slots": [],
  "reagent_hint": {
    "raw_text": "氯化钠",
    "guessed_code": "NaCl-AR",
    "guessed_name_cn": "氯化钠",
    "guessed_name_formula": "NaCl"
  },
  "params": {
    "target_mass_mg": 50000,
    "tolerance_mg": null,
    "target_vessel": "A1"
  },
  "raw_asr_text": "帮我配50克氯化钠放到A1"
}
```

- **示例（信息不完整，触发反问）**：

```json
{
  "schema_version": "1.0",
  "intent_id": "intent_20260409_002",
  "intent_type": "dispense_powder",
  "timestamp": "2026-04-09T15:31:02+08:00",
  "is_complete": false,
  "missing_slots": ["params.target_vessel"],
  "clarification_question": "请问需要把氯化钠放到哪个容器？",
  "reagent_hint": {
    "raw_text": "氯化钠",
    "guessed_code": "NaCl-AR",
    "guessed_name_cn": "氯化钠",
    "guessed_name_formula": "NaCl"
  },
  "params": {
    "target_mass_mg": 50000,
    "tolerance_mg": null,
    "target_vessel": null
  },
  "raw_asr_text": "帮我配50克氯化钠"
}
```

| intent_type 枚举 | 含义 |
|-----------------|------|
| `dispense_powder` | 单步称量分装 |
| `aliquot_powder` | 分料（1→N等份）|
| `mix_powder` | 混合（多组分→1容器）|
| `query_stock` | 查询库存 |
| `query_device_status` | 查询设备状态 |
| `save_formula` | 保存配方到配方库 |
| `cancel_task` | 取消任务 |
| `emergency_stop` | 紧急停止 |
| `unknown` | 意图无法识别，需反问 |

### 0.2 command JSON（下发给 C++ 的执行指令）

command JSON 是规则引擎在 intent_json 基础上，查药品库补全字段后生成的**任务级指令**，格式见 `shared/command_schema.json`：

- **来源**：规则引擎 + 状态机（校验 intent_json + 查药品库 + 确认设备就绪后生成）
- **内容**：任务类型（dispense/aliquot/mix/formula）、完整药品信息（来自数据库）、目标质量、目标容器
- **职责边界**：
  - AI 层只告诉 C++ **配什么、配多少、什么模式**（高层任务描述）
  - C++ 自主决定机械臂运动路径、称重闭环控制、停止时机等底层执行细节
  - AI 层**不下发动作序列**，不干涉 C++ 内部执行逻辑
- **示例（dispense）**：

```json
{
  "schema_version": "2.1",
  "command_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-04-09T15:30:46+08:00",
  "operator_id": "admin",
  "command_type": "dispense",
  "payload": {
    "reagent_code": "NaCl-AR",
    "reagent_name_cn": "氯化钠",
    "reagent_name_en": "Sodium Chloride",
    "reagent_name_formula": "NaCl",
    "purity_grade": "AR",
    "station_id": "station_3",
    "target_mass_mg": 50000,
    "tolerance_mg": 500,
    "target_vessel": "A1"
  },
  "confirmation": {
    "method": "voice",
    "confirmed_at": "2026-04-09T15:30:45+08:00"
  }
}
```

### 0.3 两层校验与约束

| 校验项 | intent_json 阶段 | command JSON 阶段 |
|--------|-----------------|-------------------|
| 药品是否存在 | ❌ 不保证 | ✅ 规则引擎查库确认 |
| 工位是否合法 | ❌ 不保证 | ✅ 状态机确认工位空闲 |
| 目标重量是否超量程 | ❌ 不保证 | ✅ 规则引擎校验范围（天平量程 220g = 220000mg）|
| 配方组分配比是否=1 | ❌ 不保证 | ✅ 规则引擎校验（mix 类型）|
| 药品字段是否完整 | ❌ LLM 仅提供 hint | ✅ 规则引擎从数据库补全所有字段 |

intent_json 未通过校验 → 拒绝，TTS 反问用户补充信息
command JSON 未通过校验 → 拒绝，不下发 C++，TTS 提示具体原因

---

## 通信方式

| 项目 | 规范 |
|------|------|
| AI层→C++控制程序 协议 | **TCP + JSON**（具体端口和帧格式与 C++ 同事对齐，开发阶段 mock-qt 用 HTTP 模拟）|
| 数据格式 | JSON，UTF-8 编码 |
| AI层→C++控制程序 地址 | `{CONTROL_ADAPTER_HOST}:{CONTROL_ADAPTER_PORT}`（默认 `localhost:9000`）|
| 认证 | 开发阶段暂不认证，生产阶段按需与 C++ 同事协商 |

> **开发阶段说明**：`mock-qt/server.py` 使用 HTTP 模拟 C++ 控制程序，方便调试。真实 C++ 程序的传输层协议（HTTP 或原始 TCP）待与同事对齐后确认，`control_client.py` 需适配实际协议。

### 通信分层说明

1. **前端 ↔ 后端**
   - 使用 `HTTP/REST + WebSocket`
   - 前端只与 FastAPI 后端交互，不直接与 C++ 控制程序通信

2. **后端 ↔ C++ 后级控制程序**
   - 使用 `TCP + JSON`
   - 后端下发任务指令（配什么、配多少、什么模式）
   - C++ 同步返回接收确认，执行完成后异步回调
   - **C++ 自主处理**：机械臂运动、称重闭环、停止时机，AI 层不干涉

3. **后端 ↔ 天平（WKC204C）**
   - 使用 `RS422-USB + MT-SICS ASCII 串口协议`（pyserial 驱动）
   - **仅用于前端实时展示天平读数**，不参与称重闭环控制
   - 称重闭环由 C++ 控制程序自主完成

4. **C++ 控制程序 ↔ 底层设备**
   - 电机驱动器：`RS485 + Modbus RTU`（或按实际驱动器协议）
   - 其他现场设备：`CAN / 串口 / TCP`
   - 属于 C++ 内部实现，AI 层不感知

---

## 通用指令结构

所有指令共享以下顶层字段：

```json
{
  "schema_version": "2.1",
  "command_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-04-09T10:30:00+08:00",
  "operator_id": "admin",
  "command_type": "<见下方枚举>",
  "payload": { ... },
  "confirmation": {
    "method": "voice",
    "confirmed_at": "2026-04-09T10:30:05+08:00"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `schema_version` | string | ✅ | 当前固定 `"2.1"`，破坏性变更升 major，新增可选字段升 minor |
| `command_id` | string (UUID v4) | ✅ | 全局唯一，C++ 控制程序用于幂等去重 |
| `timestamp` | string (ISO 8601) | ✅ | AI 层生成指令的时间，含时区 |
| `operator_id` | string | ✅ | 当前操作员标识（开发阶段默认 `admin`）|
| `command_type` | string (enum) | ✅ | 见下方枚举表 |
| `payload` | object | ✅ | 每种 command_type 有独立结构，见下方 |
| `confirmation.method` | string | ✅ | "voice"（语音确认）或 "screen"（屏幕点击） |
| `confirmation.confirmed_at` | string (ISO 8601) | ✅ | 用户确认时间 |

---

## command_type 枚举

| 值 | 含义 | 需用户确认 |
|----|------|----------|
| `dispense` | 单步称量分装（1种试剂→1容器）| ✅ |
| `aliquot` | 分料（1种试剂→N等份容器）| ✅ |
| `mix` | 混合（多种试剂→1容器，支持质量分数/摩尔分数）| ✅ |
| `formula` | 多步配方（以上操作的顺序组合）| ✅（整体确认一次）|
| `query_stock` | 查询指定试剂的库存剩余量 | ❌（查询类，直接执行）|
| `restock` | 试剂入库（更新库存量）| ✅ |
| `save_formula` | 保存当前配方到控制执行层（如需要）| ❌ |
| `cancel` | 取消当前正在执行的步骤 | ❌ |
| `emergency_stop` | 紧急停止所有动作 | ❌（立即执行）|
| `device_status` | 查询设备/天平当前状态 | ❌ |

---

## 各类型 payload 详细规范

### 1. `dispense` — 单步称量分装

```json
{
  "command_type": "dispense",
  "payload": {
    "reagent_code": "NaCl-AR",
    "reagent_name_cn": "氯化钠",
    "reagent_name_en": "Sodium Chloride",
    "reagent_name_formula": "NaCl",
    "purity_grade": "AR",
    "molar_weight_g_mol": 58.44,
    "station_id": "station_3",
    "target_mass_mg": 500,
    "tolerance_mg": 5,
    "target_vessel": "A1",
    "notes": ""
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `reagent_code` | string | ✅ | 试剂唯一编码，来自药品库（主键）|
| `reagent_name_cn` | string | ✅ | 中文名，来自药品库，冗余用于控制层日志展示 |
| `reagent_name_en` | string | ❌ | 英文名，可选 |
| `reagent_name_formula` | string | ❌ | 化学式，可选 |
| `purity_grade` | string | ❌ | 纯度等级，如 AR、GR、CP |
| `molar_weight_g_mol` | number | ❌ | 摩尔质量（g/mol），来自药品库，mix 类型时必传 |
| `station_id` | string | ❌ | 试剂当前所在工位，来自视觉识别或人工录入 |
| `target_mass_mg` | integer | ✅ | 目标质量，单位 mg，正整数 |
| `tolerance_mg` | integer | ✅ | 允许误差，单位 mg，建议不小于 1（天平分辨率 0.1mg）|
| `target_vessel` | string | ✅ | 目标容器编号（如 "A1", "B3", "main"）|
| `notes` | string | ❌ | 备注，可空 |

---

### 2. `aliquot` — 分料（1种→N份）

```json
{
  "command_type": "aliquot",
  "payload": {
    "reagent_code": "NaCl-AR",
    "reagent_name_cn": "氯化钠",
    "reagent_name_en": "Sodium Chloride",
    "reagent_name_formula": "NaCl",
    "purity_grade": "AR",
    "station_id": "station_3",
    "portions": 10,
    "mass_per_portion_mg": 1010,
    "tolerance_mg": 5,
    "target_vessels": ["A1","A2","A3","A4","A5","A6","A7","A8","A9","A10"],
    "notes": ""
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `reagent_code` | string | ✅ | 试剂唯一编码 |
| `reagent_name_cn` | string | ✅ | 中文名 |
| `portions` | integer | ✅ | 份数，2~30 |
| `mass_per_portion_mg` | integer | ✅ | 每份质量，单位 mg |
| `tolerance_mg` | integer | ✅ | 每份允许误差，单位 mg |
| `target_vessels` | array[string] | ✅ | 容器列表，长度必须等于 `portions` |

---

### 3. `mix` — 混合配方

mix 的 components 使用统一的组分结构（质量分数和摩尔分数共用，见 `shared/command_schema.json` 中的 `mix_component` 定义）。

#### 质量分数（ratio_type = "mass_fraction"）

```json
{
  "command_type": "mix",
  "payload": {
    "formula_name": "自定义混合",
    "total_mass_mg": 5000,
    "ratio_type": "mass_fraction",
    "components": [
      {
        "reagent_code": "A-AR",
        "reagent_name_cn": "试剂A",
        "reagent_name_formula": "A",
        "purity_grade": "AR",
        "station_id": "station_1",
        "fraction": 0.60,
        "calculated_mass_mg": 3000,
        "tolerance_mg": 15
      },
      {
        "reagent_code": "B-AR",
        "reagent_name_cn": "试剂B",
        "reagent_name_formula": "B",
        "purity_grade": "AR",
        "station_id": "station_2",
        "fraction": 0.40,
        "calculated_mass_mg": 2000,
        "tolerance_mg": 10
      }
    ],
    "target_vessel": "main",
    "execution_mode": "sequential"
  }
}
```

#### 摩尔分数（ratio_type = "molar_fraction"）

```json
{
  "command_type": "mix",
  "payload": {
    "formula_name": "NaCl-KCl混合",
    "total_mass_mg": 5000,
    "ratio_type": "molar_fraction",
    "components": [
      {
        "reagent_code": "NaCl-AR",
        "reagent_name_cn": "氯化钠",
        "reagent_name_en": "Sodium Chloride",
        "reagent_name_formula": "NaCl",
        "purity_grade": "AR",
        "station_id": "station_3",
        "molar_weight_g_mol": 58.44,
        "fraction": 0.60,
        "calculated_mass_mg": 2052,
        "tolerance_mg": 10
      },
      {
        "reagent_code": "KCl-AR",
        "reagent_name_cn": "氯化钾",
        "reagent_name_en": "Potassium Chloride",
        "reagent_name_formula": "KCl",
        "purity_grade": "AR",
        "station_id": "station_4",
        "molar_weight_g_mol": 74.55,
        "fraction": 0.40,
        "calculated_mass_mg": 1757,
        "tolerance_mg": 9
      }
    ],
    "target_vessel": "main",
    "execution_mode": "sequential"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `total_mass_mg` | integer | ✅ | 混合物总质量，单位 mg |
| `ratio_type` | string | ✅ | "mass_fraction" 或 "molar_fraction" |
| `components` | array | ✅ | 组分列表，至少2个 |
| `components[].reagent_code` | string | ✅ | 试剂唯一编码 |
| `components[].reagent_name_cn` | string | ✅ | 中文名 |
| `components[].molar_weight_g_mol` | number | 摩尔分数时必填 | 摩尔质量（g/mol），来自药品库，LLM不得自行填写 |
| `components[].fraction` | float | ✅ | 该组分占比（0~1，所有组分之和 = 1.0）|
| `components[].calculated_mass_mg` | integer | ✅ | AI层已换算好的实际称量质量（mg），C++控制层直接使用，无需重新计算 |
| `execution_mode` | string | ✅ | "sequential"（当前版本固定）|

> **注意**：`calculated_mass_mg` 由 AI 层从药品库查出 `molar_weight_g_mol` 后换算，并验证（各组分 `calculated_mass_mg` 之和 = `total_mass_mg` ± 1mg），C++ 控制层直接执行即可，无需重新计算。

---

### 4. `formula` — 多步配方

```json
{
  "command_type": "formula",
  "payload": {
    "formula_name": "PBS 磷酸盐缓冲液",
    "formula_id": "f-pbs-001",
    "steps": [
      {
        "step_index": 1,
        "step_name": "称量氯化钠",
        "command_type": "dispense",
        "payload": {
          "reagent_name": "氯化钠",
          "reagent_code": "NaCl-AR",
          "target_mass_mg": 8000,
          "tolerance_mg": 50,
          "target_vessel": "main"
        }
      },
      {
        "step_index": 2,
        "step_name": "称量氯化钾",
        "command_type": "dispense",
        "payload": {
          "reagent_name": "氯化钾",
          "reagent_code": "KCl-AR",
          "target_mass_mg": 200,
          "tolerance_mg": 5,
          "target_vessel": "main"
        }
      },
      {
        "step_index": 3,
        "step_name": "称量磷酸氢二钠",
        "command_type": "dispense",
        "payload": {
          "reagent_name": "磷酸氢二钠",
          "reagent_code": "Na2HPO4-AR",
          "target_mass_mg": 1440,
          "tolerance_mg": 10,
          "target_vessel": "main"
        }
      },
      {
        "step_index": 4,
        "step_name": "称量磷酸二氢钾",
        "command_type": "dispense",
        "payload": {
          "reagent_name": "磷酸二氢钾",
          "reagent_code": "KH2PO4-AR",
          "target_mass_mg": 240,
          "tolerance_mg": 5,
          "target_vessel": "main"
        }
      }
    ],
    "execution_mode": "sequential",
    "on_step_failure": "pause_and_notify"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `formula_id` | string | ❌ | 来自配方库时填写，临时配方可为 null |
| `steps[].step_index` | integer | ✅ | 从 1 开始递增 |
| `steps[].command_type` | string | ✅ | 只允许 "dispense" / "aliquot" / "mix" |
| `execution_mode` | string | ✅ | 固定 "sequential"（当前版本不支持并行配方）|
| `on_step_failure` | string | ✅ | "pause_and_notify"（暂停并通知 AI 层）或 "abort_all" |

---

### 5. `query_stock` — 查询库存

```json
{
  "command_type": "query_stock",
  "payload": {
    "reagent_code": "NaCl-AR"
  }
}
```

---

### 6. `cancel` — 取消当前步骤

```json
{
  "command_type": "cancel",
  "payload": {
    "target_command_id": "正在执行的command_id",
    "cancel_reason": "用户主动取消"
  }
}
```

---

### 7. `emergency_stop` — 紧急停止

```json
{
  "command_type": "emergency_stop",
  "payload": {}
}
```

> 控制执行层收到此指令应立即停止所有运动机构，无需返回结果后再停。

---

### 8. `device_status` — 查询设备状态

```json
{
  "command_type": "device_status",
  "payload": {}
}
```

---

## 控制执行层响应格式

### 同步响应（指令接收确认）

控制执行层收到指令后，**立即**返回接收确认（无论是否执行完）：

```json
{
  "command_id": "550e8400-e29b-41d4-a716-446655440000",
  "received_at": "2026-04-03T10:30:00.150+08:00",
  "status": "accepted",
  "message": ""
}
```

| `status` 值 | 含义 |
|-------------|------|
| `accepted` | 已接收，开始执行 |
| `rejected` | 拒绝（原因见 message，如设备忙、试剂不存在）|

### 异步回调（执行结果）

执行完成或失败后，控制执行层主动回调 AI 层：

**回调地址**：`POST http://{AI_HOST}:8000/api/device/callback`

```json
{
  "command_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "completed_at": "2026-04-03T10:30:45+08:00",
  "result": {
    "actual_mass_mg": 498,
    "deviation_mg": -2,
    "vessel": "A1"
  },
  "error": null
}
```

| `status` 值 | 含义 |
|-------------|------|
| `completed` | 执行成功 |
| `failed` | 执行失败（error 字段有描述）|
| `partial` | 部分成功（formula 多步中某步失败）|
| `cancelled` | 已取消 |

**formula 多步配方的回调**包含每步结果：

```json
{
  "command_id": "...",
  "status": "completed",
  "result": {
    "steps": [
      { "step_index": 1, "status": "completed", "actual_mass_mg": 7985 },
      { "step_index": 2, "status": "completed", "actual_mass_mg": 199 },
      { "step_index": 3, "status": "completed", "actual_mass_mg": 1441 },
      { "step_index": 4, "status": "completed", "actual_mass_mg": 238 }
    ]
  }
}
```

---

## 错误码

| 错误码 | 含义 | AI 层处理方式 |
|--------|------|--------------|
| `DEVICE_BUSY` | 设备正在执行其他指令 | TTS 提示"设备正忙，请稍候" |
| `REAGENT_NOT_FOUND` | 设备中找不到该试剂 | TTS 提示"设备中未找到该试剂" |
| `MASS_OUT_OF_RANGE` | 目标质量超出天平量程 | TTS 提示"质量超出设备范围" |
| `VESSEL_NOT_FOUND` | 容器编号不存在 | TTS 提示"容器编号无效" |
| `TIMEOUT` | 执行超时（>60s 未完成）| TTS 提示"操作超时，请检查设备" |
| `HARDWARE_ERROR` | 硬件故障 | TTS 提示"设备故障，请联系维护人员" |

---

## 版本管理规则

- **schema_version** 格式：`major.minor`
- `minor` 升级：新增可选字段，向后兼容
- `major` 升级：字段重命名/删除/类型变更，**双方必须同时升级**，提前至少 1 周通知
- 当前版本：`2.3`
- 变更记录：

| 版本 | 时间 | 变更内容 |
|------|------|---------|
| 1.0 | 2026-04-03 | 初始版本，支持 dispense/aliquot/mix/formula/query_stock/cancel/emergency_stop/device_status |
| 2.0 | 2026-04-09 | 新增意图与执行分离的两层设计：intent_json（LLM输出）+ execution_plan（规则引擎+状态机生成）；新增 intent_type 枚举；完善白名单动作校验说明 |
| 2.1 | 2026-04-09 | 全链路单位统一为 mg 整数；天平通信明确为 MT-SICS over RS422；intent_json/execution_plan 示例字段单位更正 |
| 2.2 | 2026-04-09 | 拆分 Schema 文件：新增 intent_schema.json（LLM意图格式）；command_schema.json 专用于下发C++控制层；扩展药品/试剂字段（reagent_name_cn/en/formula/purity_grade/molar_weight_g_mol/station_id 等）；mix_component 统一质量分数与摩尔分数结构；intent_json 示例更新为符合 intent_schema.json v1.0 格式（含 is_complete/missing_slots/clarification_question/reagent_hint/raw_asr_text）；新增天平数据流说明（RS422-USB 直连 Jetson，WebSocket 推前端）；控制层明确为 C++ 程序 |
| 2.3 | 2026-04-09 | 明确职责边界：AI层只下发任务级指令（配什么/配多少/什么模式），C++自主处理称重闭环和动作序列；删除 execution_plan/action_chain 概念（属于C++内部实现，不在协议范围内）；通信方式从 HTTP 更正为 TCP+JSON；删除 JWT 认证描述（开发阶段暂不认证）；天平明确为 Jetson 直连仅用于前端展示，不参与闭环；通用指令结构 schema_version 从 "1.0" 更正为 "2.1" |
