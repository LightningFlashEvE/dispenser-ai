<template>
  <div class="status-view">
    <div class="page-header">
      <h2>系统状态</h2>
      <div class="header-hint">点击右下角 AI 球可发起对话</div>
    </div>

    <!-- 第一行：天平 / 网络 / 设备状态 -->
    <div class="row-cards">
      <!-- 天平读数 -->
      <el-card class="stat-card">
        <div class="card-label">天平读数</div>
        <div class="balance-val" :class="{ stable: isBalanceStable }">
          {{ balanceValue }}<span class="unit">mg</span>
        </div>
        <div class="card-sub">{{ isBalanceStable ? '已稳定' : '未稳定' }}</div>
      </el-card>

      <!-- WebSocket 连接 -->
      <el-card class="stat-card">
        <div class="card-label">AI 后端连接</div>
        <div class="status-val" :class="isConnected ? 'ok' : 'err'">
          {{ isConnected ? '已连接' : '未连接' }}
        </div>
        <div class="card-sub">WebSocket /ws/voice</div>
      </el-card>

      <!-- 设备状态 -->
      <el-card class="stat-card">
        <div class="card-label">设备状态</div>
        <div class="status-val" :class="deviceStatusClass">
          {{ deviceStatusText }}
        </div>
        <div class="card-sub">{{ lastFetchAt ? '更新: ' + formatTime(lastFetchAt) : '等待中...' }}</div>
      </el-card>

      <!-- AI 对话状态 -->
      <el-card class="stat-card">
        <div class="card-label">AI 对话状态</div>
        <div class="dialog-badge" :class="dialogState.toLowerCase()">
          <span class="badge-dot"></span>{{ dialogStateText }}
        </div>
        <div class="card-sub">状态机: {{ deviceStore.status?.state_machine_state ?? '—' }}</div>
      </el-card>
    </div>

    <!-- 第二行：视觉工位摘要 / 当前任务 -->
    <div class="row-cards row-mid">
      <!-- 视觉工位摘要 -->
      <el-card class="mid-card">
        <div class="card-label">工位状态摘要</div>
        <div v-if="stations.length === 0" class="empty-tip">等待视觉系统连接</div>
        <div v-else class="station-grid">
          <div
            v-for="s in stations"
            :key="s.station_id"
            class="station-chip"
            :class="{ occupied: s.has_bottle }"
          >
            <span class="s-id">{{ s.station_id }}</span>
            <span class="s-state">{{ s.has_bottle ? (s.reagent_name_cn ?? '有瓶') : '空' }}</span>
          </div>
        </div>
        <div class="card-sub">{{ visionLastUpdated }}</div>
      </el-card>

      <!-- 最近任务结果 -->
      <el-card class="mid-card">
        <div class="card-label">最近任务结果</div>
        <div v-if="!latestCommandResult" class="empty-tip">暂无任务记录</div>
        <template v-else>
          <div class="task-status" :class="latestCommandResult.status">
            {{ taskStatusText }}
          </div>
          <div class="task-id">任务 {{ latestCommandResult.command_id?.slice(0, 12) }}…</div>
          <div v-if="latestCommandResult.error" class="task-err">
            {{ latestCommandResult.error.message }}
          </div>
        </template>
      </el-card>
    </div>

    <!-- 第三行：对话历史 -->
    <el-card class="history-card">
      <div class="card-label-inline">
        对话历史
        <el-button link size="small" @click="clearHistory">清空</el-button>
      </div>
      <!-- AI 反问高亮 -->
      <transition name="fade">
        <div v-if="latestQuestion" class="ai-question">
          <el-icon><QuestionFilled /></el-icon>
          {{ latestQuestion }}
        </div>
      </transition>
      <!-- 实时转写 -->
      <div v-if="realtimeCaption" class="caption-bar">
        <span class="caption-live">● 正在识别：</span>{{ realtimeCaption }}
      </div>
      <!-- 消息列表 -->
      <div ref="historyRef" class="history-list">
        <div v-if="transcript.length === 0" class="empty-tip center">暂无对话历史</div>
        <div v-for="(msg, i) in transcript" :key="i" class="history-msg" :class="msg.role">
          <div class="msg-time">{{ formatTime(msg.timestamp) }}</div>
          <div class="msg-bubble">{{ msg.text }}</div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useVoiceStore } from '@/stores/voice'
import { useVisionStore } from '@/stores/vision'
import { useDeviceStore } from '@/stores/device'

const voiceStore  = useVoiceStore()
const visionStore = useVisionStore()
const deviceStore  = useDeviceStore()

const {
  dialogState,
  realtimeCaption,
  transcript,
  latestQuestion,
  latestCommandResult,
  isConnected,
} = storeToRefs(voiceStore)

const { stations, lastUpdatedAt, balanceReading } = storeToRefs(visionStore)
const { lastFetchAt } = storeToRefs(deviceStore)

// ─── 天平 ───────────────────────────────────────────────────────
const balanceValue  = computed(() => balanceReading.value?.mass_mg.toFixed(1) ?? '0.0')
const isBalanceStable = computed(() => balanceReading.value?.stable ?? false)

// ─── 对话状态文字 ────────────────────────────────────────────────
const dialogStateText = computed(() => {
  const map: Record<string, string> = {
    IDLE: '空闲', LISTENING: '聆听中', PROCESSING: '处理中',
    ASKING: '反问中', EXECUTING: '执行中', FEEDBACK: '执行完成', ERROR: '发生错误',
  }
  return map[dialogState.value] ?? '未知'
})

// ─── 设备状态 ────────────────────────────────────────────────────
const deviceStatusText = computed(() => {
  const s = deviceStore.status?.device_status
  if (!s || s === 'unknown') return '未知'
  const map: Record<string, string> = { ready: '就绪', busy: '忙碌', error: '错误', offline: '离线' }
  return map[s] ?? s
})

const deviceStatusClass = computed(() => {
  const s = deviceStore.status?.device_status
  if (s === 'ready')  return 'ok'
  if (s === 'error')  return 'err'
  if (s === 'busy')   return 'warn'
  return 'neutral'
})

// ─── 任务结果 ────────────────────────────────────────────────────
const taskStatusText = computed(() => {
  const map: Record<string, string> = {
    completed: '✓ 完成', failed: '✗ 失败', cancelled: '取消', partial: '部分完成',
  }
  return map[latestCommandResult.value?.status ?? ''] ?? '—'
})

// ─── 视觉更新时间 ────────────────────────────────────────────────
const visionLastUpdated = computed(() =>
  lastUpdatedAt.value ? '更新: ' + formatTime(lastUpdatedAt.value) : '等待视觉推送'
)

// ─── 时间格式化 ──────────────────────────────────────────────────
function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return iso }
}

// ─── 对话历史滚动 ────────────────────────────────────────────────
const historyRef = ref<HTMLElement | null>(null)
watch(transcript, async () => {
  await nextTick()
  if (historyRef.value) historyRef.value.scrollTop = historyRef.value.scrollHeight
}, { deep: true })

// ─── 清空对话历史 ────────────────────────────────────────────────
function clearHistory(): void {
  voiceStore.reset()
}
</script>

<style scoped>
.status-view {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
  height: 100%;
  overflow: hidden;
}

.page-header {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-4);
  flex-shrink: 0;
}

.header-hint {
  font-size: 0.82rem;
  color: var(--text-secondary);
  opacity: 0.6;
}

/* ─── 第一行卡片 ─────────────────────────────────────────────── */
.row-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-3);
  flex-shrink: 0;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.card-label {
  font-size: 0.78rem;
  color: var(--text-secondary);
  opacity: 0.7;
}

.balance-val {
  font-size: 1.9rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  transition: color 0.3s;
}

.balance-val.stable { color: var(--status-success); }

.unit {
  font-size: 0.85rem;
  font-weight: 400;
  margin-left: 3px;
  opacity: 0.7;
}

.status-val {
  font-size: 1.3rem;
  font-weight: 600;
}
.status-val.ok   { color: var(--status-success); }
.status-val.err  { color: var(--status-error); }
.status-val.warn { color: var(--status-warning); }
.status-val.neutral { color: var(--text-secondary); }

.card-sub {
  font-size: 0.72rem;
  color: var(--text-secondary);
  opacity: 0.5;
  margin-top: 2px;
}

/* 对话状态徽章 */
.dialog-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 1.1rem;
  font-weight: 600;
  padding: 4px 0;
}

.badge-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #555;
  flex-shrink: 0;
}
.dialog-badge.idle       .badge-dot { background: #555; }
.dialog-badge.listening  .badge-dot { background: var(--status-success); animation: pulse 1.2s infinite; }
.dialog-badge.processing .badge-dot { background: var(--primary-blue); animation: pulse 0.8s infinite; }
.dialog-badge.asking     .badge-dot { background: var(--status-warning); animation: pulse 1.0s infinite; }
.dialog-badge.executing  .badge-dot { background: var(--primary-blue); animation: pulse 0.7s infinite; }
.dialog-badge.feedback   .badge-dot { background: var(--status-success); }
.dialog-badge.error      .badge-dot { background: var(--status-error); animation: pulse 0.4s infinite; }
.dialog-badge.idle { color: var(--text-secondary); }
.dialog-badge.listening  { color: var(--status-success); }
.dialog-badge.processing { color: var(--primary-blue); }
.dialog-badge.asking     { color: var(--status-warning); }
.dialog-badge.executing  { color: var(--primary-blue); }
.dialog-badge.feedback   { color: var(--status-success); }
.dialog-badge.error      { color: var(--status-error); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}

/* ─── 中间行 ─────────────────────────────────────────────────── */
.row-mid {
  grid-template-columns: 1fr 1fr;
  flex-shrink: 0;
}

.mid-card { display: flex; flex-direction: column; gap: 6px; }

.station-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.station-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 10px;
  border-radius: 8px;
  background: var(--bg-card-hover);
  border: 1px solid var(--border-color);
  font-size: 0.75rem;
  min-width: 56px;
}
.station-chip.occupied {
  background: rgba(34, 197, 94, 0.10);
  border-color: var(--status-success);
}
.s-id { font-weight: 600; color: var(--text-secondary); }
.s-state { color: var(--text-secondary); opacity: 0.7; font-size: 0.7rem; }

.task-status {
  font-size: 1.2rem;
  font-weight: 600;
}
.task-status.completed { color: var(--status-success); }
.task-status.failed    { color: var(--status-error); }
.task-status.cancelled { color: var(--text-secondary); }
.task-status.partial   { color: var(--status-warning); }
.task-id  { font-size: 0.75rem; color: var(--text-secondary); opacity: 0.6; }
.task-err { font-size: 0.82rem; color: var(--status-error); margin-top: 4px; }

/* ─── 对话历史 ───────────────────────────────────────────────── */
.history-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.card-label-inline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.78rem;
  color: var(--text-secondary);
  opacity: 0.7;
  margin-bottom: var(--spacing-2);
  flex-shrink: 0;
}

.ai-question {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  background: rgba(245, 158, 11, 0.10);
  border: 1px solid var(--status-warning);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
  color: var(--status-warning);
  font-size: 0.95rem;
  flex-shrink: 0;
  margin-bottom: var(--spacing-2);
}

.caption-bar {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-card-hover);
  border-radius: var(--radius-sm);
  font-size: 0.88rem;
  color: var(--text-secondary);
  flex-shrink: 0;
  margin-bottom: var(--spacing-2);
}
.caption-live { color: var(--status-success); margin-right: 6px; }

.history-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  padding-right: 4px;
}

.history-msg {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.history-msg.user      { align-items: flex-end; }
.history-msg.assistant { align-items: flex-start; }

.msg-time {
  font-size: 0.7rem;
  color: var(--text-secondary);
  opacity: 0.5;
}

.msg-bubble {
  max-width: 80%;
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: 12px;
  font-size: 0.92rem;
  line-height: 1.5;
  word-break: break-all;
}
.history-msg.user      .msg-bubble { background: #1d4ed8; color: #fff; border-bottom-right-radius: 4px; }
.history-msg.assistant .msg-bubble { background: var(--bg-card-hover); color: var(--text-main); border-bottom-left-radius: 4px; }

.empty-tip {
  font-size: 0.85rem;
  color: var(--text-secondary);
  opacity: 0.5;
}
.empty-tip.center { text-align: center; margin-top: var(--spacing-4); }

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
