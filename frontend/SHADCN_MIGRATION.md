# shadcn-vue / Tailwind CSS 迁移说明

## 当前前端结构概览

- 技术栈：Vue 3 + Vite + TypeScript，保留 Vue Router、Pinia、Axios、WebSocket、ECharts。
- 入口：`src/main.ts` 注册 Pinia、Element Plus 和 Router，`src/App.vue` 现在挂载 `AppShell`。
- 路由：`src/router/index.ts` 使用 hash history；新增 `/dashboard`，根路径重定向到 `/dashboard`。
- API：`src/services/api.ts` 统一封装 `/api/drugs`、`/api/formulas`、`/api/tasks`、`/api/logs`、`/api/device/status`、`/api/system/resources`。
- WebSocket：`src/services/websocket.ts` 保持 `/ws/voice`、`audio.commit`、`state.update`、`balance_reading` 等既有事件格式。
- Pinia：`src/stores/voice.ts` 管理语音、称重、待确认意图和 WebSocket 状态；`inventory.ts`、`formulas.ts`、`sessions.ts` 保持原有逻辑。

## shadcn-vue 引入方式

- 新增 `tailwind.config.ts`、`postcss.config.js`、`components.json`。
- `src/styles/theme.css` 引入 Tailwind layers，并定义 shadcn CSS variables，默认通过 `document.documentElement.classList.add('dark')` 使用 dark mode。
- 新增 `src/lib/utils.ts`，提供 `cn()`，基于 `clsx` 与 `tailwind-merge`。
- 新增 `src/lib/status.ts`，集中维护任务、连接、称重、资源状态的语义颜色映射。
- 新增 `src/components/ui/*`，以 shadcn-vue 风格提供 Button、Card、Badge、Progress、Tabs、Dialog、AlertDialog、Sheet、Table、Input、Textarea、Select、Separator、ScrollArea、Tooltip、Sonner。
- 新增 `src/components/common/*` 的 PageHeader、DataToolbar、EmptyState、ErrorState、LoadingState、MetricGrid 和统一导出入口，用于后续页面迁移。
- Element Plus 暂时保留全局注册，旧页面继续使用，便于分阶段迁移。

## Element Plus 到 shadcn-vue 组件映射

| Element Plus | shadcn-vue / 新组件 |
| --- | --- |
| `el-button` | `ui/button/Button.vue` |
| `el-card` / 自定义 `wf-card` | `ui/card/*` |
| `el-tag` / 自定义 badge | `ui/badge/Badge.vue` |
| `el-progress` | `ui/progress/Progress.vue` |
| `el-dialog` | `ui/dialog/Dialog.vue` |
| `ElMessageBox.confirm` | `ui/alert-dialog/AlertDialog.vue` / `ConfirmActionDialog.vue` |
| `el-table` | `ui/table/*` |
| `el-input` | `ui/input/Input.vue` |
| `el-input type="textarea"` | `ui/textarea/Textarea.vue` |
| `el-select` | `ui/select/Select.vue` |
| `el-scrollbar` | `ui/scroll-area/ScrollArea.vue` |
| `ElMessage` | `vue-sonner` / `ui/sonner/Sonner.vue` |

## 已重构页面列表

- `/dashboard`：新增现代 AI 工业控制台 POC。
- `/logs` 日志报警：已迁移为 shadcn-vue/Tailwind 表格、筛选、统计、加载态、错误态和空态，继续复用 `taskApi.list`。
- `/weight` 实时称重：新增轻量页面，复用 WebSocket 称重数据和 ECharts 趋势卡片。
- 全局框架：`AppShell` + `SidebarNav` 已使用 Tailwind/shadcn-vue 风格。
- 工程维护：已补充 ESLint 9 flat config、路由懒加载、Vite manualChunks、`.playwright-cli/` 忽略规则。

## 未重构页面列表

- `/voice` 任务执行 / 语音交互：保留原实现，保留原 WebSocket 与确认流程。
- `/inventory` 药品库存：保留旧 Element Plus 库存实现，导航名称已恢复为真实页面语义。
- `/formulas` 配方管理：保留 Element Plus 表格、表单、删除确认。
- `/vision` 视觉识别：保留旧实现。
- `/status` 系统状态：保留旧系统状态页，但已从主导航隐藏；系统资源和设备状态已合并到 Dashboard。
- `/settings` 系统设置：保留旧实现。

## Dashboard POC 数据来源

- 后端连接：`deviceApi.status()` 是否成功。
- WebSocket：`useVoiceStore().isConnected`。
- 当前称重：`balance_reading` / `balance_over_limit` 写入的 `balanceMg`、`balanceStable`、`balanceOverLimit`。
- 当前任务、今日任务、报警：`taskApi.list({ limit: 80 })`。
- 系统资源：`systemApi.resources()`；温度字段当前接口未定义，因此只保留提示，不展示假数据。
- AI 服务健康：基于 `/ws/voice` 连接状态和 `voiceStore.stateLabel` 推断。

## 安全边界

- 未修改后端 API 路径、参数、响应结构、WebSocket 地址或事件格式。
- 未新增真实设备控制逻辑。
- Dashboard 的启动、暂停入口在后端无明确接口时保持禁用，不绕过后端规则引擎。
- 停止任务只调用现有 `voiceStore.cancelTask()`，通过既有 WebSocket `cancel` 事件发送，并使用 `AlertDialog` 二次确认。
- 配方删除、库存删除、语音待确认等旧页面安全确认流程未删除。

## 风险点和后续建议

- `/inventory` 当前被放入“实时称重”导航位置只是为了匹配目标信息架构，后续建议新增独立 `WeightView`，不要复用库存页语义。
- 设备子模块状态目前只有 `DeviceStatus` 的粗粒度字段，机械臂、摄像头、TTS、LLM 等细分状态仍需要后端显式字段后才能精确展示。
- 系统资源接口没有温度字段，Dashboard 不展示假温度。
- 旧页面仍使用 Element Plus，后续迁移时应逐页替换表格、表单和确认弹窗。
- 建议下一步优先迁移配方管理页和药品库存页，因为它们包含高密度数据表和危险删除动作，适合验证 shadcn-vue 的 Table / AlertDialog / Toast 组合。
- 如果继续压缩首屏包体，建议在迁移旧页面时同步拆分 Element Plus 依赖，并逐步移除全局 Element Plus 注册。
