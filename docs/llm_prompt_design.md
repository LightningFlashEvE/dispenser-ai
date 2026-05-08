# AIExtractor Prompt 设计文档 v2.0

> **用途**：指导 `backend/app/services/ai_extractor.py` 和相关 fallback extractor 的 prompt / 输出约束。
> **当前架构**：AI 只做语言理解和字段 patch 提取；后端负责 draft 状态、完整性判断、catalog lookup、规则校验和 command 签发。
> **模型**：Qwen3-4B-Instruct-2507-Q4_K_M（通过 llama.cpp server 部署）。

---

## 1. 核心原则

- AIExtractor **只输出本轮字段 patch**，不输出最终 intent / command。
- AIExtractor 不判断 `complete` / `ready_for_review`，这些只能以后端 Validator 为准。
- AIExtractor 不写 `chemical_id`，化学品身份只能来自 Chemical Catalog lookup 或用户候选选择。
- AIExtractor 不写 `slot_id` / `motor_id` / `pump_id` / `valve_id` / `station_id` 等控制层字段。
- 用户没有明确说的字段不输出，或输出为 `null`；不要补猜。
- ASR 的 `raw_text` 与 `normalized_text` 必须保留给后端 ASR guard，不能让 normalized text 静默绕过用户确认。

---

## 2. System Prompt 模板

```
你是自动配药设备的字段提取器。
你的任务是从用户本轮输入中提取明确出现的任务字段 patch。

你不能判断任务是否完整。
你不能生成 intent JSON。
你不能生成 command JSON。
你不能写 chemical_id。
你不能写 slot_id、motor_id、pump_id、valve_id、station_id。
用户没有明确说的字段不要补猜。

只输出 JSON，不输出 Markdown、解释文字或代码块。
```

---

## 3. WEIGHING patch 输出

输入上下文：

```json
{
  "task_type": "WEIGHING",
  "current_draft": {
    "chemical_name_text": null,
    "chemical_id": null,
    "chemical_display_name": null,
    "target_mass": null,
    "mass_unit": null,
    "target_vessel": null,
    "purpose": null
  },
  "user_message": "帮我称 5g 氯化钠"
}
```

输出：

```json
{
  "patch": {
    "chemical_name_text": "氯化钠",
    "target_mass": 5,
    "mass_unit": "g"
  }
}
```

补充输入：

```text
放 A1，做标准液
```

输出：

```json
{
  "patch": {
    "target_vessel": "A1",
    "purpose": "标准液"
  }
}
```

---

## 4. DISPENSING patch 输出

输入：

```text
把氯化钠分成 3 份，每份 1g
```

输出：

```json
{
  "patch": {
    "source_material_text": "氯化钠",
    "portion_count": 3,
    "amount_per_portion": 1,
    "amount_unit": "g"
  }
}
```

补充输入：

```text
放 A1 A2 A3，做测试样品
```

输出：

```json
{
  "patch": {
    "target_vessels": ["A1", "A2", "A3"],
    "purpose": "测试样品"
  }
}
```

---

## 5. 非法字段处理

如果模型输出以下字段，后端必须丢弃并记录审计事件：

```text
chemical_id
slot_id
motor_id
pump_id
valve_id
station_id
complete
ready_for_review
command
command_json
```

示例非法输出：

```json
{
  "patch": {
    "chemical_name_text": "氯化钠",
    "chemical_id": "fake_id",
    "target_mass": 5,
    "mass_unit": "g",
    "slot_id": "S1"
  }
}
```

后端 sanitized patch 只能保留：

```json
{
  "chemical_name_text": "氯化钠",
  "target_mass": 5,
  "mass_unit": "g"
}
```

---

## 6. ASR guard 交互

语音输入进入 extractor 前后都必须保留 ASR 元数据：

```json
{
  "asr": {
    "raw_text": "我要称五克绿化钠",
    "normalized_text": "我要称5g氯化钠",
    "confidence": 0.78,
    "needs_confirmation": true
  }
}
```

规则：

- `normalized_text` 可以用于提取 patch。
- `raw_text` 必须进入 audit event。
- 如果关键字段低置信，Validator 不得直接进入 `READY_FOR_REVIEW`。
- 用户确认识别字段后，后端才解除 `needs_confirmation`。

关键字段：

```text
chemical_name_text
source_material_text
target_mass
mass_unit
target_vessel
amount_per_portion
amount_unit
target_vessels
```

---

## 7. 后端处理流程

```
用户输入 / ASR normalized_text
  ↓
Intent Router 选择任务类型或查询 route
  ↓
AIExtractor 输出 patch
  ↓
JSON parse（失败 → 返回空 patch 并记录 raw output）
  ↓
字段 whitelist 过滤
  ↓
DraftManager merge
  ↓
Chemical Catalog lookup（chemical_id 后端写入）
  ↓
Validator 判断 missing_slots / pending_confirmation_fields
  ↓
WebSocket 推 draft_update
```

---

## 8. 测试重点

- `帮我称 5g 氯化钠` 提取 `chemical_name_text` / `target_mass` / `mass_unit`。
- `放 A1，做标准液` 提取 `target_vessel` / `purpose`。
- `把氯化钠分成 3 份，每份 1g` 提取 DISPENSING source / portion / amount。
- AIExtractor 输出 `chemical_id` 时后端丢弃。
- 空 patch 不破坏已有 draft。
- ASR raw / normalized 不一致且低置信时，不直接进入 `READY_FOR_REVIEW`。
- Validator 的 `missing_slots` 不信任 AI 输出，只以后端 draft 为准。

---

## 9. 版本记录

| 版本 | 时间 | 变更 |
|------|------|------|
| 1.0 | 2026-04-09 | 初始版本。LLM 直接输出完整 intent_json、is_complete、missing_slots |
| 2.0 | 2026-05-08 | 改为 draft workflow：AIExtractor 只输出 patch；后端负责 Validator、ASR guard、catalog lookup、proposal 和 command |
