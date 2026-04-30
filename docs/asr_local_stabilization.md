# 本地 ASR 稳定化方案

> 本文档说明 dispenser-ai 项目如何在本地 whisper.cpp 输出后增加领域热词纠错层，解决中文语音识别同音/近音错字问题。

---

## 1. 架构概览

```
前端麦克风
  ↓
whisper.cpp (本地 ASR，HTTP 接口)
  ↓
raw_text（原始识别文本）
  ↓
【新增】ASR 后处理层（本地离线）
  ├─ 固定错词替换
  ├─ 中文数字归一化
  ├─ 英文单位归一化
  ├─ 语境敏感替换（个 → 克）
  └─ 领域热词模糊匹配
  ↓
normalized_text（纠错后文本）
  ↓
对话历史 / LLM 意图解析
  ↓
用户确认 → 规则引擎 → 设备执行
```

**核心原则：**
- `raw_text` **永远保留**，用于追溯和对账。
- `normalized_text` **仅用于后续意图解析和用户确认**，不直接触发设备执行。
- 所有设备动作继续走原有的**用户确认 + 规则引擎 + 状态机**流程。

---

## 2. raw_text 与 normalized_text 的区别

| 字段 | 说明 | 用途 |
|------|------|------|
| `raw_text` | whisper.cpp 原始输出，强制简体转码后的文本 | 日志追溯、前端展示、对账 |
| `normalized_text` | 经过领域纠错后的文本 | 注入对话历史、LLM 意图解析 |

**示例：**

| 用户语音 | raw_text | normalized_text |
|----------|----------|-----------------|
| "称取五克录化钠" | "称取五克录化钠" | "称取5克氯化钠" |
| "天枰去皮" | "天枰去皮" | "天平去皮" |
| "称取五个氯化钠" | "称取五个氯化钠" | "称取5克氯化钠" |

---

## 3. 热词库来源

热词库由 `DomainLexicon` 类管理，来源分为 **动态数据库** 和 **静态内置词表** 两级：

### 3.1 动态数据库（优先）

启动时自动尝试加载：

- **药品库** (`app.models.drug`)：药品中文名、英文名、化学式、别名
- **配方库** (`app.models.formula`)：配方名称

如果数据库模型尚未就绪（如当前 `app/models/` 目录缺失），自动降级到内置词表，**不会阻塞启动**。

### 3.2 静态内置词表（兜底）

位于 `backend/app/services/asr/lexicon.py`，包含：

| 类别 | 示例 |
|------|------|
| 药品名 | 氯化钠、葡萄糖、无水乙醇、碳酸氢钠 |
| 药品别名 | NaCl → 氯化钠、nacl → 氯化钠、食盐 → 氯化钠 |
| 配方名 | 生理盐水、缓冲液、复合维生素溶液 |
| 设备名 | 天平、机械臂、摄像头、工位、料仓 |
| 动作词 | 称取、加入、添加、启动、暂停、继续、停止、取消、确认、去皮、归零、初始化、复位 |
| 单位词 | 克、毫克、千克、毫升、升、g、mg、kg、ml、L |

---

## 4. 如何从药品库和配方库扩展热词

### 方式一：启动时自动加载（推荐）

在 `backend/app/ws/channels.py` 的 `voice_websocket` 中已内置：

```python
lexicon = DomainLexicon()
try:
    await lexicon.load_from_db()
except Exception:
    logger.exception("热词库数据库加载失败，使用默认词表")
```

只要 `app.models.drug` 和 `app.models.formula` 可用，启动 WebSocket 连接时就会自动加载。

### 方式二：运行时热更新

可在后台任务中定时刷新：

```python
async def refresh_lexicon(lexicon: DomainLexicon):
    await lexicon.load_from_db()
```

### 方式三：通过 REST API 更新药品/配方

药品和配方数据通过现有接口 (`POST /api/drugs`, `POST /api/formulas`) 录入后，下次加载热词库时自动生效。

**关键字段：**
- `reagent_name_cn`：药品标准中文名
- `aliases_list`：药品别名列表（最重要，用于语音模糊匹配）
- `formula_name`：配方名称

---

## 5. 如何增加常见错词

编辑 `backend/app/services/asr/normalizer.py` 中的 `FIXED_REPLACEMENTS` 字典：

```python
FIXED_REPLACEMENTS: dict[str, str] = {
    "录化钠": "氯化钠",
    "氯化拿": "氯化钠",
    "绿化钠": "氯化钠",
    "氯化纳": "氯化钠",
    "NaCl": "氯化钠",
    "nacl": "氯化钠",
    "豪克": "毫克",
    "毛克": "毫克",
    "毫可": "毫克",
    "乘取": "称取",
    "乘去": "称取",
    "撑取": "称取",
    "称去": "称取",
    "配放": "配方",
    "配芳": "配方",
    "天枰": "天平",
    "添平": "天平",
    # 在这里追加新错词...
}
```

**规则：**
- 按长度降序排列（代码中已自动排序，无需手动调整）
- 键为常见语音识别错误，值为标准写法
- 追加后运行 `pytest tests/test_asr_normalizer.py -v` 确保不破坏现有测试

---

## 6. 如何避免误纠正

系统采用多层防御机制防止过度纠正：

### 6.1 固定错词 — 仅替换词典中明确定义的错词

不会全局替换，只有列入 `FIXED_REPLACEMENTS` 的词才会被修改。

### 6.2 模糊匹配 — 多重过滤

`fuzzy_matcher.py` 中的保护措施：

1. **最小长度过滤**：只处理长度 ≥ 2 的词（`MIN_TERM_LEN = 2`），避免单字误匹配
2. **长度差异过滤**：文本子串与热词长度差 > 2 时跳过比较
3. **子串包含过滤**：如果文本子串包含热词（如 "克氯化钠" 包含 "氯化钠"），或热词包含子串，则跳过。这是为了防止正常词组被拆分。
4. **置信度阈值**：
   - ≥ 0.82：自动纠正
   - 0.65 ~ 0.82：仅提示 suggestions，不自动替换
   - < 0.65：忽略

### 6.3 语境敏感替换 — "个 → 克" 受动作词+领域词约束

`"个"` **不会全局替换为 `"克"`**。只有在以下模式才替换：

```
动作词 + 数字 + 个 + 药品名/领域词
```

例如：
- ✅ "称取五个氯化钠" → "称取5克氯化钠"
- ❌ "第一个工位" → 不改
- ❌ "打开第一个配方" → 不改

### 6.4 数字归一化 — 不修改量词序号

中文数字（一、二、两...）会转为阿拉伯数字，但这通常不会影响语义。如果业务上需要保留某些序号，可在 `number_normalizer.py` 中增加白名单逻辑。

---

## 7. 如何查看 corrections 和 suggestions

### 7.1 后端日志

每次 ASR 后处理都会在日志中输出：

```
ASR 归一化完成：raw="称取五克录化钠" normalized="称取5克氯化钠"
  corrections=2 suggestions=0 lexicon_terms=25 elapsed=0.45ms
```

日志级别为 `INFO`，位置：`backend/logs/`（或 stdout）。

日志内容包括：
- `raw`：原始识别文本
- `normalized`：纠错后文本
- `corrections`：自动纠正条数
- `suggestions`：疑似提示条数
- `lexicon_terms`：当前热词库词条总数
- `elapsed`：处理耗时（毫秒）

### 7.2 前端展示

语音输入后，用户消息气泡下方会展开 ASR 纠错详情面板：

- **识别原文**：显示 `raw_text`
- **自动纠正**：列出所有 `corrections`（错误词 → 纠正词）
- **疑似词汇**：列出所有 `suggestions`（候选词 + 相似度百分比）
- **提示文案**："已根据药品/配方热词库自动纠正，请确认后再执行。"

如果 `raw_text == normalized_text`（无纠正），则不展开详情面板。

### 7.3 WebSocket 消息格式

后端发送的 `asr.final` 消息已扩展：

```json
{
  "type": "asr.final",
  "text": "称取5克氯化钠",
  "raw_text": "称取五克录化钠",
  "normalized_text": "称取5克氯化钠",
  "corrections": [
    {
      "from": "录化钠",
      "to": "氯化钠",
      "type": "fixed_replacement",
      "confidence": 1.0,
      "reason": "固定错词纠正..."
    },
    {
      "from": "五克",
      "to": "5克",
      "type": "number_unit",
      "confidence": 1.0,
      "reason": "中文数字归一化..."
    }
  ],
  "suggestions": [],
  "needs_confirmation": true,
  "duration_ms": 1200
}
```

**兼容性说明**：旧前端只读取 `text` 字段，仍可正常工作。

---

## 8. 固定语音口令测试清单

在设备现场，可使用以下口令验证 ASR 后处理效果：

| 序号 | 口令 | 期望 normalized_text |
|------|------|----------------------|
| 1 | 称取五克氯化钠 | 称取5克氯化钠 |
| 2 | 称取五点五克氯化钠 | 称取5.5克氯化钠 |
| 3 | 称取五十毫克氯化钠 | 称取50毫克氯化钠 |
| 4 | 加入二号工位 | 加入2号工位 |
| 5 | 天平去皮 | 天平去皮 |
| 6 | 初始化设备 | 初始化设备 |
| 7 | 暂停当前任务 | 暂停当前任务 |
| 8 | 继续当前任务 | 继续当前任务 |
| 9 | 停止当前任务 | 停止当前任务 |
| 10 | 打开配方一 | 打开配方1 |
| 11 | 删除配方一 | 删除配方1 |
| 12 | 查询设备状态 | 查询设备状态 |
| 13 | 查看最近报警 | 查看最近报警 |
| 14 | 称取半克葡萄糖 | 称取0.5克葡萄糖 |
| 15 | 称取五毫克碳酸氢钠 | 称取5毫克碳酸氢钠 |

**现场验证方法：**
1. 在 Voice 界面点击麦克风按钮，说出口令
2. 停止录音后，观察用户消息气泡下方是否显示【识别原文】和【自动纠正】
3. 核对 `normalized_text` 是否与期望一致
4. 若有 suggestions（疑似词汇），点击确认执行前检查是否为预期药品/配方

---

## 9. 文件清单

| 文件 | 说明 |
|------|------|
| `backend/app/services/asr/__init__.py` | ASR 后处理模块入口 |
| `backend/app/services/asr/lexicon.py` | 领域热词库（DomainLexicon） |
| `backend/app/services/asr/number_normalizer.py` | 中文数字与单位归一化 |
| `backend/app/services/asr/fuzzy_matcher.py` | 热词模糊匹配（difflib） |
| `backend/app/services/asr/normalizer.py` | ASR 归一化主入口 |
| `backend/app/ws/channels.py` | 接入 WebSocket ASR 流程 |
| `backend/tests/test_asr_normalizer.py` | 单元测试（37 条用例） |
| `frontend/src/services/websocket.ts` | WebSocket 类型扩展（Correction/Suggestion） |
| `frontend/src/stores/voice.ts` | 前端状态管理（asrMeta） |
| `frontend/src/views/VoiceView.vue` | 语音界面（纠错详情展示） |
| `docs/asr_local_stabilization.md` | 本文档 |

---

## 10. 约束与边界

1. **不接云端 ASR**：所有处理均在本地 Jetson Orin NX 完成
2. **不删除 whisper.cpp**：原始 ASR 引擎完全保留
3. **不修改设备控制协议**：后级 C++ 控制程序通信格式不变
4. **不修改规则引擎和状态机**：`normalized_text` 只是替代 `raw_text` 进入原有对话链路
5. **不绕过用户确认**：`needs_confirmation` 标记存在纠正/建议时始终为 `true`，但确认流程仍由前端按钮触发
6. **不覆盖 raw_text**：原始文本始终保留在 `asr.final` 消息的 `raw_text` 字段
7. **不引入大型依赖**：仅使用 Python 标准库 `difflib.SequenceMatcher`，无需额外安装包
8. **不修改 shadcn Dashboard**：仅修改 VoiceView.vue 的语音交互区域
