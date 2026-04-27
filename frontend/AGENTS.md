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
| Element Plus | 2+ | 工业触摸屏界面组件 |
| echarts / wavesurfer.js | 最新 | 波形、状态与数据可视化 |

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
- 显示当前状态：待机 / 聆听 / 识别中 / 思考中 / 回复中 / 等待确认 / 执行中 / 错误
- 录音开始前先检查 WebSocket 连接；若未连接，立即提示，不进入“假录音”状态
- 用户停止录音后统一提交 ASR，转写完成后落成一条用户消息，再进入 AI 回复
- 显示语音输入按钮、连接异常提示、待确认操作与执行反馈

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
- `confirm`（用户点击"确认执行"按钮，触发命令阶段）

### 后端→前端
- `state.update`
- `asr.partial`
- `asr.final`
- `chat.delta`
- `chat.done`
- `pending_intent`
- `pending_cleared`
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

---

## 施工约束

1. **禁止 `any` 类型**，TypeScript 严格模式
2. **禁止在组件中直接调用 API**，统一走 store 或 service
3. **WebSocket 消息统一在 `websocket.ts` 管理**
4. **音频处理统一在 `audio.ts` 封装**
5. **前端只做展示与交互，不承载业务决策逻辑**
6. **界面必须适配全屏浏览器运行**
