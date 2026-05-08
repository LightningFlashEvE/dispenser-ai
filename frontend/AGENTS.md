# frontend/AGENTS.md — 前端施工指南

> 进入前端施工前，**必须先读根目录 AGENTS.md**，再读本文件。

---

## 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| Vue3 | 3.4+ | 本地网页 UI 框架（Composition API） |
| Vite | 5+ | 构建工具 |
| TypeScript | 5+ | 严格模式，禁止 any |
| Pinia | 2+ | 状态管理 |
| Vue Router | 4+ | 页面路由 |
| Tailwind + shadcn-vue | 当前项目版本 | 主视觉和常规组件体系 |
| Element Plus | 2+ | 仅用于复杂表格、表单、弹窗、分页 |
| ECharts | 最新 | 主图表库 |
| wavesurfer.js | 最新 | 波形展示 |
| lucide-vue-next | 最新 | 主图标库 |

**不要随意引入新的 UI / 图表库。** 新增视觉、图表、图标需求优先复用 Tailwind + shadcn-vue、ECharts、lucide-vue-next；Element Plus 只在复杂数据录入和管理页面使用。

---

## 前端定位

前端运行于 **工业触摸屏全屏浏览器**，采用本地网页界面。其职责是：

1. 展示语音交互状态
2. 展示转写文本、AI 反问和执行结果
3. 展示库存、配方、操作日志和设备状态
4. 展示视觉识别结果（工位有无、二维码识别结果）
5. 为操作员提供触摸确认与管理入口

---

## 建议目录结构

```
frontend/
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── router/
│   ├── stores/
│   ├── services/
│   │   ├── api.ts              # REST API 封装
│   │   ├── websocket.ts        # WebSocket 管理
│   │   └── audio.ts            # 麦克风与音频播放封装
│   ├── views/
│   │   ├── VoiceView.vue       # 语音交互主界面
│   │   ├── InventoryView.vue   # 库存管理
│   │   ├── FormulasView.vue    # 配方库
│   │   ├── LogsView.vue        # 操作日志
│   │   ├── VisionView.vue      # 工位与二维码识别结果
│   │   ├── DeviceView.vue      # 设备状态 / 2D工位图（预留菜单，暂不实现）
│   │   └── SettingsView.vue    # 系统设置
│   └── components/
│       ├── voice/
│       ├── inventory/
│       ├── vision/
│       ├── device/             # 预留，DeviceView 子组件放这里
│       └── common/
```

---

## 核心页面

### VoiceView.vue
- 采用类似网页 AI 的对话流：用户消息气泡 → AI 流式回复气泡 → 待确认操作卡片
- 显示当前状态：待机 / 聆听 / 识别中 / 思考中 / 回复中 / 收集任务信息 / 等待用户确认 / 规则校验中 / 执行中 / 错误
- 录音开始前先检查 WebSocket 连接；若未连接，立即提示，不进入“假录音”状态
- 麦克风只在浏览器安全上下文中可用：本机 `localhost` 可用 HTTP，局域网 IP 访问必须走 HTTPS；错误提示要区分安全上下文、浏览器 API 缺失和用户权限拒绝
- 用户停止录音后统一提交 ASR，转写完成后落成一条用户消息，再进入 AI 回复
- 显示语音输入按钮、连接异常提示、draft_update 结构化确认卡片、catalog 候选选择、ASR 低置信提示与执行反馈
- 前端不根据 AI 自然语言判断任务是否完整；只使用后端 `draft_update` / `ready_for_review` / `pending_confirmation_fields` / `catalog_candidates` 状态展示确认入口
- WEIGHING / DISPENSING 确认卡片必须展示用户输入、系统 catalog 匹配、CAS/等级、任务字段、状态和确认/修改/取消按钮
- 如果 `asr.needs_confirmation=true`，先提示“该任务包含语音识别修正内容，请确认”，确认识别内容不能直接等同于确认执行任务

### VisionView.vue
- 显示工位有无瓶状态
- 显示二维码识别出的药品 ID
- 显示二维码中心坐标和角度
- 显示最近一次识别时间与状态

### InventoryView / FormulasView / LogsView
- 管理库存、配方和操作日志

### DeviceView.vue（预留，暂不实现）
- 2D 工位图：展示龙门臂当前位置、工位占用状态、天平实时读数
- 数据来源：C++ 控制程序通过 TCP 推送的实时状态 JSON（格式待与同事对齐后定义）
- **当前版本：菜单项占位，页面内容留空或显示"功能开发中"**

---

## WebSocket 消息重点

### 前端→后端
- `[binary frame]`：PCM Int16 音频帧
- `audio.commit`
- `chat.user_text`
- `barge_in`
- `cancel`
- `cancel_pending`
- `confirm`（用户确认结构化任务卡片；后端仍必须先规则校验）

### 后端→前端
- `state.update`
- `asr.partial`
- `asr.final`
- `chat.delta`
- `chat.done`
- `pending_intent`
- `pending_cleared`
- `draft_update`
- `catalog_candidates`
- `rule_checking`
- `slot_filling`
- `dialog_reply`（对话阶段 LLM 自然语言回复，不含执行意图）
- `tts.chunk`
- `tts.done`
- `tts_end`
- `user_message`
- `command_sent`
- `command_result`
- `error`

### 兼容说明
- 旧协议 `audio_chunk` / `audio_end` / `transcript` / `stt_final` 仍可兼容一段时间，但新代码默认走二进制音频帧 + `audio.commit` + `asr.final`

---

## 状态管理建议

```typescript
interface VoiceState {
  dialogState: 'idle' | 'listening' | 'recognizing' | 'thinking' | 'speaking' | 'awaiting_confirmation' | 'executing' | 'error'
  asrPartial: string
  messages: ChatMessage[]
  pendingIntent: PendingIntent | null
  currentDraft: TaskDraft | null
  draftStatus: 'COLLECTING' | 'NEEDS_FIELD_CONFIRMATION' | 'READY_FOR_REVIEW' | 'PROPOSAL_CREATED' | 'RULE_CHECKING' | 'COMMAND_SENT' | 'CANCELLED' | 'FAILED' | null
  isConnected: boolean
  micError: MicError | null
}

interface VisionState {
  stations: StationStatus[]
  lastUpdatedAt: string | null
}
```

---

## UI 约束

1. **大按钮、大字号、少层级**，适配工业触摸屏
2. **操作状态必须醒目**，避免误判当前执行阶段
3. **反问信息必须突出显示**，方便用户快速补充
4. **视觉结果必须清晰标识工位号和识别结果**
5. **错误信息必须可读，不得只显示代码**
6. **确认卡片必须结构化展示后端状态**，不得只靠 AI 自然语言提示执行关键操作
7. **用户确认后显示规则校验中 / 已下发执行 / 规则失败**，不要再显示“等待审批”

---

## 施工约束

1. **禁止 `any` 类型**，TypeScript 严格模式
2. **禁止在组件中直接调用 API**，统一走 store 或 service
3. **WebSocket 消息统一在 `websocket.ts` 管理**
4. **音频处理统一在 `audio.ts` 封装**
5. **前端只做展示与交互，不承载业务决策逻辑**
6. **界面必须适配全屏浏览器运行**
7. **禁止新增 UI / 图表 / 图标库**，除非先更新根目录和本文件规则并说明必要性
