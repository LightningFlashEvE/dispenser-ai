<template>
  <div class="voice-view">
    <header class="top-bar">
      <div class="top-bar-left">
        <span class="state-badge" :class="`state-badge--${normalizedState}`">
          <span class="state-pulse" v-if="isActiveState"></span>
          {{ voiceStore.stateLabel }}
        </span>
        <span v-if="voiceStore.asrPartial" class="asr-partial">"{{ voiceStore.asrPartial }}..."</span>
      </div>
      <div class="top-bar-right">
        <div v-if="voiceStore.balanceMg !== null" class="balance-chip"
          :class="{ 'balance-chip--over': voiceStore.balanceOverLimit }">
          <span class="balance-label">天平</span>
          <span class="balance-val">{{ voiceStore.balanceMg.toFixed(0) }}</span>
          <span class="balance-unit">mg</span>
          <span v-if="voiceStore.balanceStable" class="balance-stable">稳定</span>
        </div>
        <button class="icon-btn" title="会话历史" @click="showSessionList = true">
          <el-icon><ChatLineRound /></el-icon>
        </button>
      </div>
    </header>

    <transition name="slide-down">
      <div v-if="voiceStore.errorMsg" class="error-banner">⚠ {{ voiceStore.errorMsg }}</div>
    </transition>

    <transition name="slide-down">
      <div v-if="voiceStore.micError" class="mic-error-banner">
        <el-icon class="mic-error-icon"><Microphone /></el-icon>
        <span class="mic-error-text">{{ voiceStore.micError.message }}</span>
        <button class="mic-error-retry" @click="onMicRetry">重试</button>
        <button class="mic-error-dismiss" @click="voiceStore.clearMicError">×</button>
      </div>
    </transition>

    <transition name="slide-down">
      <div v-if="voiceStore.currentDraft" class="draft-card">
        <div class="draft-header">
          <div>
            <span class="draft-label">任务草稿</span>
            <span class="draft-type">{{ taskTypeLabel }}</span>
          </div>
          <span class="draft-status" :class="`draft-status--${draftStatusTone}`">
            {{ draftStatusLabel }}
          </span>
        </div>
        <div class="draft-body">
          <div v-if="hasDraftAsrConfirmation" class="draft-asr-warning">
            <span class="draft-asr-title">该任务包含语音识别修正内容，请确认。</span>
            <span v-if="voiceStore.currentDraft.asr?.raw_text" class="draft-asr-raw">
              原始识别：{{ voiceStore.currentDraft.asr.raw_text }}
            </span>
          </div>
          <div v-for="row in draftRows" :key="row.label" class="draft-row">
            <span class="draft-field">{{ row.label }}</span>
            <span class="draft-value" :class="{ 'draft-value--missing': row.missing }">{{ row.value }}</span>
            <span v-if="row.needsConfirmation" class="draft-field-confirm">待确认</span>
          </div>
        </div>
        <div class="draft-actions">
          <button class="btn btn--confirm" :disabled="!canConfirmDraft" @click="voiceStore.confirmDraft">
            {{ draftConfirmLabel }}
          </button>
          <button class="btn btn--secondary" @click="focusModify">修改</button>
          <button class="btn btn--cancel" @click="voiceStore.cancelDraft">取消</button>
        </div>
      </div>
    </transition>

    <transition name="slide-down">
      <div v-if="voiceStore.pendingIntent" class="pending-card">
        <div class="pending-header">
          <span class="pending-label">待确认操作</span>
          <span class="pending-type">{{ voiceStore.pendingIntent.intent_type }}</span>
        </div>
        <div class="pending-body">
          <div v-if="voiceStore.pendingIntent.drug" class="pending-row">
            <span class="pending-field">药品</span>
            <span class="pending-value">
              {{ voiceStore.pendingIntent.drug.reagent_name_cn }}
              <span v-if="voiceStore.pendingIntent.drug.station_id" class="pending-station">
                工位 {{ voiceStore.pendingIntent.drug.station_id }}
              </span>
            </span>
          </div>
          <div v-for="(v, k) in filteredParams" :key="k" class="pending-row">
            <span class="pending-field">{{ paramLabel(String(k)) }}</span>
            <span class="pending-value">{{ formatParamVal(String(k), v) }}</span>
          </div>
          <div class="pending-expires">有效期至 {{ formatExpiry(voiceStore.pendingIntent.expires_at) }}</div>
        </div>
        <div class="pending-actions">
          <button class="btn btn--confirm" @click="voiceStore.confirm">✓ 确认执行</button>
          <button class="btn btn--cancel" @click="voiceStore.cancelPending">✗ 取消</button>
        </div>
      </div>
    </transition>

    <div class="chat-area" ref="chatEl">
      <div v-if="voiceStore.messages.length === 0" class="chat-empty">
        <el-icon class="chat-empty-icon"><Microphone /></el-icon>
        <div class="chat-empty-text">像和网页 AI 对话一样，点麦克风说话，停止后会先转写成你的消息，再开始回复；也可以直接输入文字</div>
      </div>
      <div v-for="msg in voiceStore.messages" :key="msg.id"
        class="msg-row" :class="`msg-row--${msg.role}`">
        <template v-if="msg.role === 'user'">
          <div class="msg-bubble msg-bubble--user">
            <div class="msg-text">{{ msg.text }}</div>
            <!-- ASR 纠错详情（仅语音输入且存在纠错时显示） -->
            <div v-if="msg.asrMeta && msg.asrMeta.needsConfirmation" class="asr-meta">
              <div class="asr-meta-divider" />
              <div class="asr-raw">识别原文：{{ msg.asrMeta.rawText }}</div>
              <div v-if="msg.asrMeta.corrections.length" class="asr-corrections">
                <div class="asr-section-title">自动纠正</div>
                <div v-for="(c, i) in msg.asrMeta.corrections" :key="i" class="asr-correction-item">
                  <span class="asr-from">{{ c.from }}</span>
                  <span class="asr-arrow">→</span>
                  <span class="asr-to">{{ c.to }}</span>
                </div>
              </div>
              <div v-if="msg.asrMeta.suggestions.length" class="asr-suggestions">
                <div class="asr-section-title">疑似词汇</div>
                <div v-for="(s, i) in msg.asrMeta.suggestions" :key="i" class="asr-suggestion-item">
                  <span class="asr-sug-text">{{ s.text }}</span>
                  <span class="asr-arrow">→</span>
                  <span class="asr-sug-candidate">{{ s.candidate }}</span>
                  <span class="asr-sug-confidence">{{ (s.confidence * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <div class="asr-hint">已根据药品/配方热词库自动纠正，请确认后再执行。</div>
            </div>
            <div class="msg-time">{{ fmtTime(msg.timestamp) }}</div>
          </div>
        </template>
        <template v-else-if="msg.role === 'assistant'">
          <div class="msg-avatar">AI</div>
          <div class="msg-bubble msg-bubble--ai" :class="{ 'msg-bubble--streaming': msg.isStreaming }">
            <div class="msg-text">{{ msg.text }}<span v-if="msg.isStreaming" class="typing-cursor">▋</span></div>
            <div class="msg-time">{{ fmtTime(msg.timestamp) }}</div>
          </div>
        </template>
        <template v-else>
          <div class="msg-system" :class="{ 'msg-system--error': msg.isError }">{{ msg.text }}</div>
        </template>
      </div>
    </div>

    <!-- Session list panel (right slide-in) -->
    <SessionList
      :visible="showSessionList"
      @close="showSessionList = false"
      @new="onNewSession"
      @switch="onSwitchSession"
    />

    <div class="input-area">
      <div class="composer-shell" :class="{ 'composer-shell--dictating': isDictationMode }">
        <transition name="composer-swap" mode="out-in">
          <div v-if="isDictationMode" key="dictation" class="dictation-panel">
            <div class="dictation-wave" aria-hidden="true">
              <DictationWaveCanvas :is-active="voiceStore.isRecording" :level="voiceStore.micLevel" />
            </div>
            <div class="dictation-copy">
              <div class="dictation-eyebrow">听写中</div>
              <div class="dictation-title">{{ dictationTitle }}</div>
              <div class="dictation-subtitle">{{ dictationSubtitle }}</div>
            </div>
          </div>
          <div v-else key="text" class="text-input-wrap">
            <input ref="textInputEl" v-model="textInput" class="text-input" :placeholder="inputPlaceholder"
              maxlength="500" @keydown.enter.exact="sendText" />
            <button class="btn btn--send" :disabled="!textInput.trim() || isSending" @click="sendText">发送</button>
          </div>
        </transition>
      </div>
      <button class="voice-btn"
        :title="voiceStore.isRecording ? '点击结束听写并发送' : '点击开始听写'"
        :class="{ 'voice-btn--recording': voiceStore.isRecording }"
        @click="toggleRecording">
        <LissajousAvatar :is-active="voiceStore.isRecording" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useVoiceStore } from '@/stores/voice'
import { useSessionsStore } from '@/stores/sessions'
import SessionList from '@/components/voice/SessionList.vue'
import LissajousAvatar from '@/components/voice/LissajousAvatar.vue'
import DictationWaveCanvas from '@/components/voice/DictationWaveCanvas.vue'
import { Microphone, ChatLineRound } from '@element-plus/icons-vue'

const voiceStore = useVoiceStore()
const sessionsStore = useSessionsStore()
const chatEl = ref<HTMLElement | null>(null)
const textInputEl = ref<HTMLInputElement | null>(null)
const textInput = ref('')
const showSessionList = ref(false)
const modifyMode = ref(false)

onMounted(async () => {
  await sessionsStore.loadSessions()
})

async function onNewSession(): Promise<void> {
  showSessionList.value = false
  const newId = await sessionsStore.createSession()
  voiceStore.clearMessages()
  voiceStore.switchSession(newId)
  await sessionsStore.loadSessions()
}

async function onSwitchSession(sessionId: string): Promise<void> {
  showSessionList.value = false
  sessionsStore.setCurrentSession(sessionId)
  voiceStore.clearMessages()
  voiceStore.switchSession(sessionId)
  try {
    const detail = await sessionsStore.getSessionDetail(sessionId)
    if (detail.messages && detail.messages.length > 0) {
      voiceStore.loadHistory(detail.messages)
    }
  } catch (e) {
    console.error('加载会话历史失败:', e)
  }
}

const normalizedState = computed<string>(() => {
  const s = String(voiceStore.sessionState).toLowerCase()
  if (['listening', 'recognizing'].includes(s)) return 'listening'
  if (['thinking', 'processing'].includes(s)) return 'thinking'
  if (['speaking', 'feedback'].includes(s)) return 'speaking'
  if (s === 'awaiting_confirmation') return 'confirm'
  if (s === 'executing') return 'executing'
  if (s === 'error') return 'error'
  return 'idle'
})
const isActiveState = computed(() => ['listening', 'thinking', 'speaking', 'executing'].includes(normalizedState.value))
const isDictationMode = computed(() => voiceStore.isRecording)
const dictationTitle = computed(() => {
  if (voiceStore.asrPartial) return voiceStore.asrPartial
  if (voiceStore.isRecording) return '正在听写，请直接说出你的需求'
  return '正在整理听写内容'
})
const dictationSubtitle = computed(() => {
  if (voiceStore.isRecording) return '再次点击右侧按钮，结束听写并发送'
  return '请稍候，马上把你的话整理成一条消息'
})
const inputPlaceholder = computed(() => (
  modifyMode.value ? '输入要修改的字段，例如 质量改成 3g 或 目标容器改成 B2' : '输入文字发送...'
))
const taskTypeLabel = computed(() => {
  const taskType = voiceStore.currentDraft?.task_type
  if (taskType === 'WEIGHING') return '称量'
  if (taskType === 'DISPENSING') return '分料'
  if (taskType === 'MIXING') return '混合'
  return '任务'
})
const draftStatusLabel = computed(() => {
  const status = voiceStore.currentDraft?.status
  const map: Record<string, string> = {
    COLLECTING: '正在收集信息',
    READY_FOR_REVIEW: '等待用户确认',
    NEEDS_FIELD_CONFIRMATION: '等待识别确认',
    PROPOSAL_CREATED: '正在校验任务规则',
    VERIFYING: '正在校验任务规则',
    DISPATCHED: '已下发执行',
    CANCELLED: '已取消',
    FAILED: '规则校验失败，不允许执行',
  }
  return status ? (map[status] ?? status) : ''
})
const draftStatusTone = computed(() => {
  const status = voiceStore.currentDraft?.status
  if (status === 'NEEDS_FIELD_CONFIRMATION') return 'asr'
  if (status === 'READY_FOR_REVIEW') return 'review'
  if (status === 'PROPOSAL_CREATED' || status === 'VERIFYING') return 'proposal'
  if (status === 'DISPATCHED') return 'review'
  if (status === 'CANCELLED') return 'cancelled'
  if (status === 'FAILED') return 'failed'
  return 'collecting'
})
const draftRows = computed(() => {
  const draft = voiceStore.currentDraft
  const data = draft?.current_draft ?? {}
  const missing = new Set(draft?.missing_slots ?? [])
  const pending = new Set(draft?.pending_confirmation_fields ?? [])
  return [
    { label: '化学品', value: String(data.chemical_name ?? '待补充'), missing: missing.has('chemical_name'), needsConfirmation: pending.has('chemical_name') },
    { label: '目标质量', value: formatDraftMass(data.target_mass, data.mass_unit), missing: missing.has('target_mass') || missing.has('mass_unit'), needsConfirmation: pending.has('target_mass') || pending.has('mass_unit') },
    { label: '目标容器', value: String(data.target_vessel ?? '待补充'), missing: missing.has('target_vessel'), needsConfirmation: pending.has('target_vessel') },
    { label: '用途', value: String(data.purpose ?? '待补充'), missing: missing.has('purpose'), needsConfirmation: pending.has('purpose') },
  ]
})
const hasDraftAsrConfirmation = computed(() => Boolean(voiceStore.currentDraft?.asr?.needs_confirmation))
const canConfirmDraft = computed(() => Boolean(
  voiceStore.currentDraft?.ready_for_review || hasDraftAsrConfirmation.value,
))
const draftConfirmLabel = computed(() => (
  voiceStore.currentDraft?.status === 'PROPOSAL_CREATED'
    ? '规则校验中'
    : hasDraftAsrConfirmation.value ? '确认识别内容' : '✓ 确认'
))

const scrollBottom = () => nextTick(() => { if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight })
watch(() => voiceStore.messages.length, scrollBottom)
watch(() => voiceStore.messages.map((m) => m.text).join(''), scrollBottom)

function onVoiceStart() {
  void voiceStore.startRecording()
}

function toggleRecording(): void {
  if (voiceStore.isRecording) {
    voiceStore.stopRecording()
  } else {
    void onVoiceStart()
  }
}

async function onMicRetry(): Promise<void> {
  voiceStore.clearMicError()
  try {
    await voiceStore.initAudio()
    await voiceStore.startRecording()
  } catch (e) {
    console.error('麦克风重试失败:', e)
  }
}

const isSending = ref(false)
function sendText() {
  const t = textInput.value.trim()
  if (!t || !voiceStore.isConnected || isSending.value) return
  isSending.value = true
  textInput.value = ''
  modifyMode.value = false
  voiceStore.sendText(t)
  setTimeout(() => { isSending.value = false }, 300)
}

function focusModify() {
  modifyMode.value = true
  nextTick(() => textInputEl.value?.focus())
}

const PARAM_LABELS: Record<string, string> = {
  target_mass_mg: '目标质量', tolerance_mg: '允差', total_mass_mg: '总质量',
  target_vessel: '目标容器', ratio_type: '配比类型',
}
const filteredParams = computed(() => {
  const p = voiceStore.pendingIntent?.params ?? {}
  return Object.fromEntries(Object.entries(p).filter(([, v]) => v !== null && v !== undefined && v !== ''))
})
function paramLabel(k: string) { return PARAM_LABELS[k] ?? k }
function formatParamVal(k: string, v: unknown) { return k.endsWith('_mg') && typeof v === 'number' ? `${v} mg` : String(v) }
function formatDraftMass(value: unknown, unit: unknown) {
  if (value === null || value === undefined || value === '') return '待补充'
  return `${value} ${unit ?? ''}`.trim()
}
function formatExpiry(iso: string) {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
}
function fmtTime(iso: string) {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
</script>

<style scoped>
.voice-view { display: flex; flex-direction: column; height: 100%; overflow: hidden; background: var(--wf-bg-page); }
.top-bar { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; border-bottom: 1px solid var(--wf-border-dark); flex-shrink: 0; gap: 12px; min-height: 56px; }
.top-bar-left, .top-bar-right { display: flex; align-items: center; gap: 12px; }
.state-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 4px; font-size: 12.8px; font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase; }
.state-badge--idle     { background: #f0f0f0; color: var(--wf-text-muted); }
.state-badge--listening { background: rgba(20, 110, 245, 0.1); color: var(--wf-blue); }
.state-badge--thinking  { background: rgba(255, 107, 0, 0.1); color: var(--wf-orange); }
.state-badge--speaking  { background: rgba(0, 215, 34, 0.1); color: var(--wf-green); }
.state-badge--confirm   { background: rgba(255, 107, 0, 0.1); color: var(--wf-orange); }
.state-badge--executing { background: rgba(122, 61, 255, 0.1); color: var(--wf-purple); }
.state-badge--error     { background: rgba(238, 29, 54, 0.1); color: var(--wf-red); }
.state-pulse { width: 6px; height: 6px; border-radius: 50%; background: currentColor; animation: pulse 1s ease-in-out infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
.asr-partial { font-size: 13px; color: var(--wf-text-muted); font-style: italic; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.balance-chip { display: flex; align-items: center; gap: 4px; padding: 4px 10px; border: 1px solid var(--wf-border-dark); border-radius: 4px; font-size: 12px; }
.balance-chip--over { border-color: var(--wf-red); background: #ffe8e8; }
.balance-label { color: var(--wf-text-muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
.balance-val { font-weight: 600; font-size: 14px; color: var(--wf-text-main); }
.balance-unit { color: var(--wf-text-muted); font-size: 11px; }
.balance-stable { color: var(--wf-green); font-size: 11px; background: rgba(0, 215, 34, 0.1); padding: 1px 4px; border-radius: 2px; }
.icon-btn { width: 32px; height: 32px; border: 1px solid var(--wf-border-dark); border-radius: 4px; background: var(--wf-bg-page); cursor: pointer; font-size: 14px; display: flex; align-items: center; justify-content: center; }
.icon-btn:hover { background: var(--wf-bg-panel); }
.error-banner { background: #ffe8e8; border-bottom: 1px solid var(--wf-red); padding: 8px 20px; font-size: 13px; color: var(--wf-red); flex-shrink: 0; }
.mic-error-banner { background: #fff0e8; border-bottom: 1px solid var(--wf-orange); padding: 10px 20px; font-size: 13px; color: #c25000; flex-shrink: 0; display: flex; align-items: center; gap: 8px; }
.mic-error-icon { font-size: 16px; }
.mic-error-text { flex: 1; }
.mic-error-retry { background: var(--wf-orange); color: var(--wf-white); border: none; border-radius: 4px; padding: 4px 12px; font-size: 12px; font-weight: 600; cursor: pointer; }
.mic-error-retry:hover { background: #e05e00; }
.mic-error-dismiss { background: none; border: none; font-size: 16px; color: #c25000; cursor: pointer; padding: 0 4px; opacity: 0.7; }
.mic-error-dismiss:hover { opacity: 1; }
.slide-down-enter-active, .slide-down-leave-active { transition: all 0.2s; }
.slide-down-enter-from, .slide-down-leave-to { transform: translateY(-8px); opacity: 0; }
.pending-card { margin: 12px 20px 0; border: 1px solid var(--wf-border-dark); border-radius: 8px; overflow: hidden; flex-shrink: 0; background: var(--wf-bg-page); box-shadow: var(--wf-shadow-cascade); }
.draft-card { margin: 12px 20px 0; border: 1px solid var(--wf-border-dark); border-radius: 8px; overflow: hidden; flex-shrink: 0; background: var(--wf-bg-page); box-shadow: var(--wf-shadow-cascade); }
.draft-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 16px; background: var(--wf-bg-panel); border-bottom: 1px solid var(--wf-border-dark); }
.draft-label { font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: var(--wf-text-muted); margin-right: 8px; }
.draft-type { font-size: 13px; font-weight: 700; color: var(--wf-text-main); }
.draft-status { font-size: 12px; font-weight: 700; border-radius: 4px; padding: 3px 8px; }
.draft-status--collecting { color: var(--wf-blue); background: rgba(20, 110, 245, 0.1); }
.draft-status--asr { color: var(--wf-orange); background: rgba(255, 107, 0, 0.12); }
.draft-status--review { color: var(--wf-orange); background: rgba(255, 107, 0, 0.12); }
.draft-status--proposal { color: var(--wf-green); background: rgba(0, 215, 34, 0.1); }
.draft-status--cancelled { color: var(--wf-text-muted); background: #f0f0f0; }
.draft-status--failed { color: var(--wf-red); background: rgba(238, 29, 54, 0.1); }
.draft-body { padding: 12px 16px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 16px; }
.draft-asr-warning { grid-column: 1 / -1; border: 1px solid rgba(255, 107, 0, 0.28); background: rgba(255, 107, 0, 0.08); color: #a64600; border-radius: 6px; padding: 8px 10px; display: flex; flex-direction: column; gap: 3px; font-size: 12.5px; }
.draft-asr-title { font-weight: 700; }
.draft-asr-raw { color: var(--wf-text-muted); }
.draft-row { display: flex; align-items: center; gap: 10px; min-width: 0; font-size: 14px; }
.draft-field { width: 72px; color: var(--wf-text-muted); font-size: 12px; letter-spacing: 0.5px; flex-shrink: 0; }
.draft-value { min-width: 0; color: var(--wf-text-main); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.draft-value--missing { color: var(--wf-orange); font-weight: 500; }
.draft-field-confirm { flex-shrink: 0; font-size: 11px; font-weight: 700; color: var(--wf-orange); border: 1px solid rgba(255, 107, 0, 0.32); background: rgba(255, 107, 0, 0.08); border-radius: 3px; padding: 1px 5px; }
.draft-actions { display: flex; gap: 10px; padding: 10px 16px; border-top: 1px solid var(--wf-border-dark); }
.pending-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; background: var(--wf-orange); color: var(--wf-white); }
.pending-label { font-size: 11px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; }
.pending-type { font-size: 12px; background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 3px; }
.pending-body { padding: 12px 16px; display: flex; flex-direction: column; gap: 6px; }
.pending-row { display: flex; align-items: center; gap: 12px; font-size: 14px; }
.pending-field { width: 80px; color: var(--wf-text-muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; flex-shrink: 0; }
.pending-value { color: var(--wf-text-main); font-weight: 500; }
.pending-station { margin-left: 8px; font-size: 11px; background: rgba(20, 110, 245, 0.1); color: var(--wf-blue); padding: 1px 6px; border-radius: 3px; }
.pending-expires { font-size: 11px; color: var(--wf-text-muted); margin-top: 4px; }
.pending-actions { display: flex; gap: 10px; padding: 10px 16px; border-top: 1px solid #ffe0c8; }
.btn { padding: 10px 20px; border: none; border-radius: 4px; font-size: 14px; font-weight: 600; cursor: pointer; transition: transform 0.15s, background 0.15s, box-shadow 0.15s; }
.btn:hover { transform: translateY(-4px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.btn--confirm { background: var(--wf-blue); color: var(--wf-white); flex: 1; font-size: 15px; padding: 12px; }
.btn--confirm:hover { background: var(--wf-blue-hover); }
.btn--cancel  { background: #f0f0f0; color: var(--wf-text-muted); }
.btn--secondary { background: var(--wf-bg-panel); color: var(--wf-text-main); border: 1px solid var(--wf-border-dark); }
.btn--confirm:disabled { background: #ccc; cursor: not-allowed; transform: none; box-shadow: none; }
.btn--send { background: var(--wf-blue); color: var(--wf-white); padding: 10px 18px; white-space: nowrap; }
.btn--send:hover { background: var(--wf-blue-hover); }
.btn--send:disabled { background: #ccc; cursor: not-allowed; transform: none; box-shadow: none; }
.chat-area { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; scroll-behavior: smooth; }
.chat-empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--wf-text-muted); padding: 40px; }
.chat-empty-icon { font-size: 40px; }
.chat-empty-text { font-size: 14px; text-align: center; max-width: 280px; line-height: 1.6; }
.msg-row { display: flex; align-items: flex-end; gap: 8px; }
.msg-row--user { justify-content: flex-end; }
.msg-row--assistant { justify-content: flex-start; }
.msg-row--system { justify-content: center; }
.msg-avatar { width: 32px; height: 32px; border-radius: 50%; background: var(--wf-blue); color: var(--wf-white); display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; }
.msg-bubble { max-width: 70%; padding: 10px 14px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.msg-bubble--user { background: var(--wf-blue); color: var(--wf-white); border-radius: 8px 8px 0 8px; }
.msg-bubble--ai { background: var(--wf-bg-panel); border: 1px solid var(--wf-border-dark); color: var(--wf-text-main); border-radius: 8px 8px 8px 0; }
.msg-bubble--streaming { border-color: var(--wf-blue); }
.msg-text { font-size: 15px; line-height: 1.55; white-space: pre-wrap; word-break: break-word; }
.msg-time { font-size: 11px; margin-top: 4px; opacity: 0.6; }
.typing-cursor { animation: blink 0.8s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }
.msg-system { font-size: 12px; color: var(--wf-text-muted); background: var(--wf-bg-panel); padding: 4px 12px; border-radius: 12px; border: 1px solid var(--wf-border-dark); }
.msg-system--error { color: var(--wf-red); background: #ffe8e8; border-color: var(--wf-red); }
.input-area { flex-shrink: 0; padding: 16px 20px 24px; display: flex; align-items: center; gap: 12px; background: transparent; }
.composer-shell { flex: 1; min-width: 0; }
.composer-shell--dictating { display: flex; }
.text-input-wrap { flex: 1; display: flex; gap: 12px; }
.text-input { flex: 1; border: 1px solid var(--wf-border-dark); border-radius: 28px; padding: 16px 24px; font-size: 16px; outline: none; background: var(--wf-bg-panel); transition: border-color 0.15s; box-shadow: inset 0 1px 4px rgba(0,0,0,0.03); color: var(--wf-text-main); }
.text-input:focus { border-color: var(--wf-blue); }
.btn--send { border-radius: 28px; padding: 0 24px; font-size: 15px; }
.dictation-panel {
  flex: 1;
  width: 100%;
  min-width: 0;
  min-height: 64px;
  border-bottom: 1px solid rgba(184, 198, 219, 0.22);
  padding: 8px 2px 10px;
  display: flex;
  align-items: center;
  overflow: hidden;
  position: relative;
}
.dictation-copy {
  min-width: 0;
  width: 100%;
  padding: 0 22px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  position: relative;
  z-index: 1;
}
.dictation-eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: rgba(184, 198, 219, 0.68);
}
.dictation-title {
  font-size: 15px;
  line-height: 1.35;
  color: var(--wf-text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dictation-subtitle {
  font-size: 12px;
  line-height: 1.35;
  color: var(--wf-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dictation-wave {
  position: absolute;
  inset: 0 18px;
  z-index: 0;
  pointer-events: none;
  opacity: 0.9;
}
.voice-btn { flex-shrink: 0; width: 80px; height: 80px; border: none; border-radius: 50%; background: transparent; cursor: pointer; display: flex; align-items: center; justify-content: center; padding: 0; transition: all 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275); margin-left: 8px; }
.voice-btn:hover:not(.voice-btn--disabled) { transform: scale(1.05); box-shadow: 0 4px 12px rgba(20, 110, 245, 0.3); }
.voice-btn--recording { animation: recording-pulse 1.5s infinite; }
.voice-btn--recording:hover:not(.voice-btn--disabled) { transform: scale(1.05); box-shadow: 0 4px 12px rgba(238, 29, 54, 0.3); }
@keyframes recording-pulse { 0% { box-shadow: 0 0 0 0 rgba(238,29,54,0.4); } 70% { box-shadow: 0 0 0 12px rgba(238,29,54,0); } 100% { box-shadow: 0 0 0 0 rgba(238,29,54,0); } }
@keyframes composer-swap-in {
  from { opacity: 0; transform: translateY(6px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.composer-swap-enter-active { animation: composer-swap-in 0.2s ease-out; }
.composer-swap-leave-active { transition: opacity 0.14s ease-in; }
.composer-swap-leave-to { opacity: 0; }
.voice-btn--disabled { opacity: 0.5; cursor: not-allowed; background: var(--wf-gray-300); }
.audio-btn-icon { font-size: 22px; }

.asr-meta { margin-top: 8px; padding-top: 8px; border-top: 1px dashed rgba(255,255,255,0.25); font-size: 12.5px; }
.asr-meta-divider { display: none; }
.asr-raw { color: rgba(255,255,255,0.75); margin-bottom: 6px; }
.asr-section-title { color: rgba(255,255,255,0.6); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin: 6px 0 4px; }
.asr-correction-item, .asr-suggestion-item { display: flex; align-items: center; gap: 4px; margin: 2px 0; flex-wrap: wrap; }
.asr-from { color: #ffd6d6; text-decoration: line-through; }
.asr-to { color: #c8ffd8; font-weight: 600; }
.asr-sug-text { color: #fff3cd; }
.asr-sug-candidate { color: #d4edda; font-weight: 600; }
.asr-sug-confidence { color: rgba(255,255,255,0.5); font-size: 11px; }
.asr-arrow { color: rgba(255,255,255,0.5); font-size: 11px; }
.asr-hint { margin-top: 6px; color: #ffe0b2; font-size: 11.5px; font-weight: 500; }

@media (max-width: 900px) {
  .input-area { padding: 12px 16px 20px; gap: 10px; }
  .dictation-panel { padding: 8px 0 10px; }
  .dictation-copy { padding: 0 18px; }
  .dictation-wave { inset: 0 14px; }
  .voice-btn { width: 72px; height: 72px; margin-left: 0; }
  .draft-body { grid-template-columns: 1fr; }
  .draft-actions { flex-direction: column; }
}
</style>
