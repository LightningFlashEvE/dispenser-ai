# LLM System Prompt 设计文档 v1.0

> **用途**：指导 `backend/app/services/ai/llm.py` 的 prompt 工程实现
> **对应 Schema**：`shared/intent_schema.json` v1.0
> **模型**：Qwen3-4B-Instruct-2507-Q4_K_M（当前选型，通过 llama.cpp server 部署）

---

## 1. 设计原则

- LLM **只做语义理解和槽位提取**，不做业务校验（药品存不存在由规则引擎查库）
- 输出**严格 JSON**，不包含任何 Markdown、代码块或解释文字
- 质量单位**统一 mg 整数**，LLM 负责把用户说的"克/g/毫克"全部换算
- 信息不足时**不猜测**，明确标记 `is_complete: false` 并给出中文反问
- 上下文（工位快照）由后端在每次调用前动态注入，LLM 不依赖训练记忆

---

## 2. System Prompt 模板

> 后端每次调用 llama.cpp server 时，将 `{STATION_SNAPSHOT}` 替换为实时工位状态，其他字段固定。

```
你是一台粉末自动配药设备的操作助手。你的唯一职责是理解操作员的语音指令，并将其转换为结构化 JSON 格式输出。

## 当前工位状态
{STATION_SNAPSHOT}

## 输出规则

1. 只输出 JSON，不输出任何说明文字、代码块标记（```）或换行前缀
2. JSON 结构严格按照下方格式，不增减字段
3. 所有质量单位统一转换为毫克（mg）整数：
   - 用户说"50克" → target_mass_mg: 50000
   - 用户说"500毫克" → target_mass_mg: 500
   - 用户说"0.5克" → target_mass_mg: 500
4. 如果用户提供的信息不足以完成任务，将 is_complete 设为 false，在 missing_slots 中列出缺失项，在 clarification_question 中用简洁中文提问
5. reagent_hint.raw_text 填写用户说的原始药品描述，guessed_code 和 guessed_name_cn 按你的理解填写，可以为 null

## 意图类型说明

- dispense：称量一种药品放入容器（需要：药品名、质量、目标容器）
- aliquot：将一种药品分装成 N 等份（需要：药品名、份数、每份质量）
- mix：多种药品按比例混合（需要：各组分名称和占比、总质量）
- query_stock：查询库存，无需其他参数
- device_status：查询设备状态，无需其他参数
- formula：保存配方，无需其他参数
- cancel：取消当前任务，无需其他参数
- emergency_stop：紧急停止，无需其他参数
- unknown：无法理解用户意图时使用

## 输出 JSON 格式

{
  "schema_version": "1.0",
  "intent_id": "{INTENT_ID}",
  "intent_type": "<意图类型>",
  "timestamp": "{TIMESTAMP}",
  "is_complete": true 或 false,
  "missing_slots": [],
  "clarification_question": null 或 "<中文反问>",
  "reagent_hint": {
    "raw_text": "<用户说的药品名>",
    "guessed_code": "<猜测编码或null>",
    "guessed_name_cn": "<猜测中文名或null>",
    "guessed_name_formula": "<猜测化学式或null>"
  },
  "params": {<见下方各意图的参数结构>},
  "raw_asr_text": "{RAW_ASR_TEXT}",
  "confidence": 0.0~1.0
}

## 各意图的 params 结构

dispense:
  { "target_mass_mg": <整数或null>, "tolerance_mg": <整数或null>, "target_vessel": "<容器编号或null>" }

aliquot:
  { "portions": <整数或null>, "mass_per_portion_mg": <整数或null>, "tolerance_mg": <整数或null>, "target_vessels": [<容器列表>或null] }

mix:
  {
    "total_mass_mg": <整数或null>,
    "ratio_type": "mass_fraction" 或 "molar_fraction" 或 null,
    "components": [ { "raw_text": "<组分描述>", "fraction": <0~1的小数或null> } ],
    "target_vessel": "<容器编号或null>"
  }

query_stock:
  { "raw_text": "<用户描述的药品或null>" }

其他意图（cancel/emergency_stop/device_status/formula/unknown）:
  {}
```

---

## 3. 工位快照注入格式（`{STATION_SNAPSHOT}`）

后端从视觉层获取当前工位状态后，格式化为以下字符串注入 prompt：

**有药品的工位：**
```
- station_1: 氯化钠 (NaCl-AR)，库存约 45000mg
- station_2: 氯化钾 (KCl-AR)，库存约 120000mg
- station_3: 磷酸氢二钠 (Na2HPO4-AR)，库存约 80000mg
- station_4: 空
- station_5: 空
称重工位: weighing_station（空闲）
```

**全部为空时：**
```
当前所有工位均为空，请先放置药品。
```

**注入策略：只注入视觉识别到的工位**（不注入整个数据库），保持 prompt 简短。若工位识别失败（相机异常），注入提示：
```
工位状态未知（视觉识别暂不可用），请人工确认药品位置。
```

---

## 4. 对话历史格式（补槽用）

补槽过程中，后端将历史轮次以 `messages` 数组传给 llama.cpp server：

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},           # 含工位快照
    {"role": "user",   "content": "帮我配氯化钠"},            # 第1轮用户输入
    {"role": "assistant", "content": '{"intent_type":"dispense","is_complete":false,...}'},
    {"role": "user",   "content": "50克，放到A1"},            # 第2轮补充
]
```

后端在拼接时**只传 JSON 字符串**作为 assistant 消息，不传 TTS 播报文本。

**截断规则（方案A - 任务级清空）：**
- 任务完成/取消/出错 → 清空 `messages` 列表（只保留 system prompt）
- 补槽超过 `DIALOG_MAX_ROUNDS=8` 轮 → 清空并 TTS 告知用户重新开始
- 每次调用前重新注入最新工位快照（工位状态可能已变化）

---

## 5. 典型场景示例

### 场景1：信息完整，一次成功

用户说：「帮我配50克氯化钠放到A1」

LLM 输出：
```json
{
  "schema_version": "1.0",
  "intent_id": "intent_20260409_001",
  "intent_type": "dispense",
  "timestamp": "2026-04-09T10:30:00+08:00",
  "is_complete": true,
  "missing_slots": [],
  "clarification_question": null,
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
  "raw_asr_text": "帮我配50克氯化钠放到A1",
  "confidence": 0.97
}
```

---

### 场景2：缺少目标容器，触发反问

用户说：「帮我配50克氯化钠」

LLM 输出：
```json
{
  "schema_version": "1.0",
  "intent_id": "intent_20260409_002",
  "intent_type": "dispense",
  "timestamp": "2026-04-09T10:30:10+08:00",
  "is_complete": false,
  "missing_slots": ["params.target_vessel"],
  "clarification_question": "请问需要放到哪个容器？",
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
  "raw_asr_text": "帮我配50克氯化钠",
  "confidence": 0.95
}
```

用户补充：「放A1」

LLM 输出（第2轮，信息完整）：
```json
{
  "schema_version": "1.0",
  "intent_id": "intent_20260409_002",
  "intent_type": "dispense",
  "timestamp": "2026-04-09T10:30:18+08:00",
  "is_complete": true,
  "missing_slots": [],
  "clarification_question": null,
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
  "raw_asr_text": "放A1",
  "confidence": 0.99
}
```

---

### 场景3：混合配方，含摩尔比

用户说：「配5克的NaCl和KCl混合，摩尔比6:4，放main」

LLM 输出：
```json
{
  "schema_version": "1.0",
  "intent_id": "intent_20260409_003",
  "intent_type": "mix",
  "timestamp": "2026-04-09T10:31:00+08:00",
  "is_complete": true,
  "missing_slots": [],
  "clarification_question": null,
  "reagent_hint": {
    "raw_text": "NaCl和KCl",
    "guessed_code": null,
    "guessed_name_cn": "氯化钠和氯化钾",
    "guessed_name_formula": "NaCl+KCl"
  },
  "params": {
    "total_mass_mg": 5000,
    "ratio_type": "molar_fraction",
    "components": [
      { "raw_text": "NaCl", "fraction": 0.6 },
      { "raw_text": "KCl", "fraction": 0.4 }
    ],
    "target_vessel": "main"
  },
  "raw_asr_text": "配5克的NaCl和KCl混合，摩尔比6:4，放main",
  "confidence": 0.91
}
```

---

### 场景4：别名识别

用户说：「配100毫克食盐到B3」

LLM 输出：
```json
{
  "schema_version": "1.0",
  "intent_id": "intent_20260409_004",
  "intent_type": "dispense",
  "timestamp": "2026-04-09T10:32:00+08:00",
  "is_complete": true,
  "missing_slots": [],
  "clarification_question": null,
  "reagent_hint": {
    "raw_text": "食盐",
    "guessed_code": "NaCl-AR",
    "guessed_name_cn": "氯化钠",
    "guessed_name_formula": "NaCl"
  },
  "params": {
    "target_mass_mg": 100,
    "tolerance_mg": null,
    "target_vessel": "B3"
  },
  "raw_asr_text": "配100毫克食盐到B3",
  "confidence": 0.89
}
```

> 注意：`reagent_hint.guessed_code` 是 LLM 猜的，规则引擎仍需查库验证。若数据库里 `食盐` 在 aliases 字段里，则匹配成功；否则以数据库为准。

---

### 场景5：分料

用户说：「把氯化钠分10份，每份500毫克」

LLM 输出：
```json
{
  "schema_version": "1.0",
  "intent_id": "intent_20260409_005",
  "intent_type": "aliquot",
  "timestamp": "2026-04-09T10:33:00+08:00",
  "is_complete": true,
  "missing_slots": [],
  "clarification_question": null,
  "reagent_hint": {
    "raw_text": "氯化钠",
    "guessed_code": "NaCl-AR",
    "guessed_name_cn": "氯化钠",
    "guessed_name_formula": "NaCl"
  },
  "params": {
    "portions": 10,
    "mass_per_portion_mg": 500,
    "tolerance_mg": null,
    "target_vessels": null
  },
  "raw_asr_text": "把氯化钠分10份，每份500毫克",
  "confidence": 0.96
}
```

> `target_vessels: null` → 规则引擎自动从视觉层获取10个空闲工位填充

---

### 场景6：紧急停止

用户说：「停！」或「紧急停止」

LLM 输出：
```json
{
  "schema_version": "1.0",
  "intent_id": "intent_20260409_006",
  "intent_type": "emergency_stop",
  "timestamp": "2026-04-09T10:34:00+08:00",
  "is_complete": true,
  "missing_slots": [],
  "clarification_question": null,
  "reagent_hint": null,
  "params": {},
  "raw_asr_text": "停！",
  "confidence": 0.99
}
```

---

## 6. 后端实现要点（`llm.py`）

### llama.cpp server 调用结构

```python
response = httpx.post(
    f"{LLM_BASE_URL}/chat/completions",
    json={
        "messages": messages,          # system + 历史轮次 + 当前用户输入
        "stream": False,
        "response_format": {"type": "json_object"},
        "temperature": 0.1,            # 低温度，减少随机性，保证 JSON 格式稳定
        "max_tokens": 512,             # 限制输出 token 数，intent_json 不需要很长
    },
    timeout=30.0,
)
```

### 关键参数说明

| 参数 | 值 | 原因 |
|------|----|------|
| `temperature` | 0.1 | 结构化 JSON 输出要求一致性，低温度减少格式错乱 |
| `response_format` | `{"type": "json_object"}` | OpenAI 兼容的 JSON 模式，强制模型只输出合法 JSON |
| `max_tokens` | 512 | intent_json 通常 200~400 tokens，留余量 |

### 输出后处理流程

```
LLM 输出字符串
  ↓
JSON 解析（失败 → 重试一次，仍失败 → 返回 unknown intent）
  ↓
jsonschema 校验（对照 shared/intent_schema.json）
  ↓
intent_id / timestamp / raw_asr_text 与后端注入值核对（防止 LLM 篡改）
  ↓
返回 IntentResult 到规则引擎
```

### 重试策略

- LLM 输出 JSON 解析失败：**重试一次**，追加 user 消息 `"请只输出 JSON，不要其他文字"`
- 第二次仍失败：返回 `intent_type: unknown`，TTS 提示"没有理解您的意思，请再说一次"
- 不无限重试，避免占用 GPU

---

## 7. 需要在代码里处理的边界情况

| 情况 | 处理方式 |
|------|---------|
| 用户说单位"g"（ASCII）vs "克"（中文） | prompt 里统一列举，LLM 处理 |
| 用户说"半克" | LLM 换算为 500，罕见情况可能失败，规则引擎兜底拒绝非整数 |
| 用户说配方名"PBS" | `intent_type: dispense`，`reagent_hint.raw_text: "PBS"`，规则引擎查配方库 |
| 用户输入纯噪音/无意义语音 | LLM 输出 `intent_type: unknown`，`confidence < 0.5` |
| mix 组分比例之和 ≠ 1.0 | LLM 尽量归一化，规则引擎再做精确校验 |
| 同时说两个任务"先配NaCl再配KCl" | LLM 只提取第一个任务，说明 `clarification_question: "我先理解为配氯化钠，KCl需要完成后再说"` |

---

## 8. 版本记录

| 版本 | 时间 | 变更 |
|------|------|------|
| 1.0 | 2026-04-09 | 初始版本。System prompt 模板、工位快照注入格式、对话历史格式（方案A任务级清空）、6个典型场景示例、后端实现要点 |
