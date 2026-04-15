<template>
  <!-- 悬浮球容器，可拖拽 -->
  <div
    ref="orbWrapRef"
    class="floating-orb-wrap"
    :style="orbStyle"
    @mousedown="onDragStart"
    @touchstart.passive="onTouchStart"
    @click.stop="togglePanel"
  >
    <!-- AI 动态球：canvas 直接撑满容器，clip-path 裁成圆 -->
    <LissajousOrb
      class="orb-canvas"
      :dialog-state="dialogState"
      :mic-analyser="null"
      :tts-analyser="null"
      :min-radius="0.16"
      :max-radius="0.44"
      :show-background="false"
    />
  </div>

  <!-- 对话面板（Teleport 到 body，避免被 orb 的 overflow 裁切） -->
  <Teleport to="body">
    <transition name="panel-fade">
      <div
        v-if="panelOpen"
        class="ai-panel"
        :style="panelStyle"
        @click.stop
      >
        <!-- 标题栏 -->
        <div class="panel-header">
          <span class="panel-title">AI 对话</span>
          <!-- TODO: 后续移植时在此处接入语音按钮，当前仅文本模式 -->
          <el-tag size="small" type="info" class="mode-tag">文本模式</el-tag>
          <el-button circle size="small" @click="togglePanel" style="margin-left:auto">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>

        <!-- 连接状态栏 -->
        <div class="panel-conn" :class="{ connected: isConnected }">
          {{ isConnected ? '● 已连接' : '○ 未连接，等待重连...' }}
        </div>

        <!-- 消息列表 -->
        <div ref="msgListRef" class="panel-messages">
          <div v-if="transcript.length === 0" class="panel-empty">暂无对话，请在下方输入</div>
          <div
            v-for="(msg, idx) in transcript"
            :key="idx"
            class="panel-msg"
            :class="msg.role"
          >
            <div class="msg-role">{{ msg.role === 'user' ? '我' : 'AI' }}</div>
            <div class="msg-text">{{ msg.text }}</div>
          </div>
          <!-- AI 反问高亮 -->
          <div v-if="latestQuestion" class="panel-question">
            <el-icon><QuestionFilled /></el-icon>
            {{ latestQuestion }}
          </div>
        </div>

        <!-- 输入区 -->
        <div class="panel-input-row">
          <el-input
            v-model="inputText"
            placeholder="输入指令，例如：称量氯化钠 500mg"
            :disabled="!isConnected || isSending"
            @keydown.enter.prevent="handleSend"
            size="large"
            clearable
          />
          <el-button
            type="primary"
            size="large"
            :loading="isSending"
            :disabled="!isConnected || !inputText.trim()"
            @click="handleSend"
          >
            发送
          </el-button>
        </div>

        <!-- 语音入口预留区域 -->
        <!-- TODO: 移植到 Jetson 后在此处挂载 startRecording / stopRecording
             当前文本模式不显示，预留注释供后续接入
             <VoiceTrigger v-if="featureVoiceEnabled" @transcript="handleTranscript" />
        -->
      </div>
    </transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useVoiceStore } from '@/stores/voice'
import { sendJson } from '@/services/websocket'
import LissajousOrb from '@/components/voice/LissajousOrb.vue'

// ─── Store ───────────────────────────────────────────────────────
const voiceStore = useVoiceStore()
const { dialogState, transcript, latestQuestion, isConnected } = storeToRefs(voiceStore)

// ─── 面板开关 ─────────────────────────────────────────────────────
const panelOpen = ref(false)
function togglePanel(): void {
  if (!isDragging.value) panelOpen.value = !panelOpen.value
}

// ─── 输入与发送 ───────────────────────────────────────────────────
const inputText = ref('')
const isSending = ref(false)
const msgListRef = ref<HTMLElement | null>(null)

async function handleSend(): Promise<void> {
  const text = inputText.value.trim()
  if (!text || !isConnected.value) return
  isSending.value = true
  // 发送文本指令给后端 WebSocket，后端以 transcript 类型处理
  sendJson({ type: 'transcript', text })
  // 立即把用户消息塞入历史（后端会再发 stt_final 确认，不会重复，因为 stt_final 会更新 caption 而非 addMessage）
  voiceStore.addMessage({ role: 'user', text, timestamp: new Date().toISOString() })
  inputText.value = ''
  isSending.value = false
  await nextTick()
  scrollBottom()
}

function scrollBottom(): void {
  if (msgListRef.value) {
    msgListRef.value.scrollTop = msgListRef.value.scrollHeight
  }
}

watch(transcript, async () => {
  await nextTick()
  scrollBottom()
}, { deep: true })

// ─── 拖拽 ─────────────────────────────────────────────────────────
const STORAGE_KEY = 'floating-orb-pos'
const ORB_SIZE = 112

const pos = ref({ x: 0, y: 0 })
const isDragging = ref(false)
let dragOffset = { x: 0, y: 0 }
let dragStartPos = { x: 0, y: 0 }
let dragMoved = false
const orbWrapRef = ref<HTMLElement | null>(null)

function clampPos(x: number, y: number): { x: number; y: number } {
  const maxX = window.innerWidth  - ORB_SIZE - 8
  const maxY = window.innerHeight - ORB_SIZE - 8
  return {
    x: Math.max(8, Math.min(x, maxX)),
    y: Math.max(8, Math.min(y, maxY)),
  }
}

function loadPos(): void {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved) as { x: number; y: number }
      pos.value = clampPos(parsed.x, parsed.y)
      return
    }
  } catch { /* 读取失败时用默认位置 */ }
  // 默认右下角
  pos.value = clampPos(window.innerWidth - ORB_SIZE - 24, window.innerHeight - ORB_SIZE - 24)
}

function savePos(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pos.value))
  } catch { /* 存储失败忽略 */ }
}

function onDragStart(e: MouseEvent): void {
  if (e.button !== 0) return
  dragOffset = { x: e.clientX - pos.value.x, y: e.clientY - pos.value.y }
  dragStartPos = { x: e.clientX, y: e.clientY }
  dragMoved = false
  isDragging.value = false
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}

function onDragMove(e: MouseEvent): void {
  const dx = Math.abs(e.clientX - dragStartPos.x)
  const dy = Math.abs(e.clientY - dragStartPos.y)
  if (dx > 4 || dy > 4) {
    isDragging.value = true
    dragMoved = true
  }
  if (!dragMoved) return
  pos.value = clampPos(e.clientX - dragOffset.x, e.clientY - dragOffset.y)
}

function onDragEnd(): void {
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
  if (dragMoved) savePos()
  setTimeout(() => { isDragging.value = false }, 50)
}

// 触摸支持
let touchId: number | null = null
function onTouchStart(e: TouchEvent): void {
  if (e.touches.length !== 1) return
  const t = e.touches[0]
  touchId = t.identifier
  dragOffset = { x: t.clientX - pos.value.x, y: t.clientY - pos.value.y }
  dragStartPos = { x: t.clientX, y: t.clientY }
  dragMoved = false
  isDragging.value = false
  window.addEventListener('touchmove', onTouchMove, { passive: false })
  window.addEventListener('touchend', onTouchEnd)
}

function onTouchMove(e: TouchEvent): void {
  const t = Array.from(e.touches).find(tt => tt.identifier === touchId)
  if (!t) return
  e.preventDefault()
  const dx = Math.abs(t.clientX - dragStartPos.x)
  const dy = Math.abs(t.clientY - dragStartPos.y)
  if (dx > 6 || dy > 6) { isDragging.value = true; dragMoved = true }
  if (!dragMoved) return
  pos.value = clampPos(t.clientX - dragOffset.x, t.clientY - dragOffset.y)
}

function onTouchEnd(): void {
  window.removeEventListener('touchmove', onTouchMove)
  window.removeEventListener('touchend', onTouchEnd)
  if (dragMoved) savePos()
  setTimeout(() => { isDragging.value = false }, 50)
}

// 窗口大小变化时重新 clamp
function onResize(): void {
  pos.value = clampPos(pos.value.x, pos.value.y)
}

onMounted(() => {
  loadPos()
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
})

// ─── 样式 ─────────────────────────────────────────────────────────
const orbStyle = computed(() => ({
  left: `${pos.value.x}px`,
  top:  `${pos.value.y}px`,
  cursor: isDragging.value ? 'grabbing' : 'grab',
}))

// 面板在球旁边弹出，根据屏幕位置自动选左/右上/下
const PANEL_W = 360
const PANEL_H = 480
const panelStyle = computed(() => {
  const { x, y } = pos.value
  const spaceRight = window.innerWidth - x - ORB_SIZE
  const spaceBottom = window.innerHeight - y
  const left = spaceRight > PANEL_W + 12 ? x + ORB_SIZE + 12 : Math.max(8, x - PANEL_W - 12)
  const top  = spaceBottom > PANEL_H + 12 ? y : Math.max(8, y + ORB_SIZE - PANEL_H)
  return {
    left: `${left}px`,
    top:  `${top}px`,
    width: `${PANEL_W}px`,
    height: `${PANEL_H}px`,
  }
})
</script>

<style scoped>
/* ─── 悬浮容器 ─────────────────────────────────────────────────── */
.floating-orb-wrap {
  position: fixed;
  z-index: 9000;
  width: 112px;
  height: 112px;
  user-select: none;
  -webkit-user-select: none;
  border-radius: 50%;
  /* 发光效果直接用 filter，不影响内部 canvas 尺寸 */
  filter: drop-shadow(0 0 14px rgba(130, 80, 255, 0.5));
  transition: filter 0.3s;
}

.floating-orb-wrap:hover {
  filter: drop-shadow(0 0 22px rgba(160, 100, 255, 0.75));
}

/* canvas 撑满容器，clip-path 裁成圆形 */
.orb-canvas,
:deep(.lissajous-orb) {
  width: 100% !important;
  height: 100% !important;
  clip-path: circle(50% at 50% 50%);
  display: block;
}

/* ─── 面板（Teleport 挂到 body，scoped 仍然生效） ─────────────── */
:global(.ai-panel) {
  position: fixed;
  z-index: 9001;
  background: #0e1117;
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 16px;
  box-shadow: 0 8px 48px rgba(0,0,0,0.6);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

:global(.panel-header) {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  flex-shrink: 0;
}

:global(.panel-title) {
  font-size: 0.95rem;
  font-weight: 600;
  color: #e0e0e0;
}

:global(.mode-tag) {
  font-size: 0.72rem;
}

:global(.panel-conn) {
  padding: 6px 16px;
  font-size: 0.78rem;
  color: #666;
  background: rgba(0,0,0,0.25);
  flex-shrink: 0;
}
:global(.panel-conn.connected) { color: #22c55e; }

:global(.panel-messages) {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

:global(.panel-empty) {
  color: #555;
  text-align: center;
  margin-top: 40px;
  font-size: 0.88rem;
}

:global(.panel-msg) {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

:global(.panel-msg.user) { align-items: flex-end; }
:global(.panel-msg.assistant) { align-items: flex-start; }

:global(.msg-role) {
  font-size: 0.72rem;
  color: #666;
}

:global(.msg-text) {
  max-width: 85%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 0.92rem;
  line-height: 1.5;
  word-break: break-all;
}

:global(.panel-msg.user .msg-text) {
  background: #1d4ed8;
  color: #fff;
  border-bottom-right-radius: 4px;
}

:global(.panel-msg.assistant .msg-text) {
  background: #1e2230;
  color: #d0d0d0;
  border-bottom-left-radius: 4px;
}

:global(.panel-question) {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid #f59e0b;
  border-radius: 10px;
  padding: 10px 14px;
  color: #f59e0b;
  font-size: 0.92rem;
  line-height: 1.5;
}

:global(.panel-input-row) {
  display: flex;
  gap: 8px;
  padding: 10px 16px 14px;
  border-top: 1px solid rgba(255,255,255,0.08);
  flex-shrink: 0;
}

/* 面板入场动画 */
:global(.panel-fade-enter-active),
:global(.panel-fade-leave-active) {
  transition: opacity 0.18s, transform 0.18s;
}
:global(.panel-fade-enter-from),
:global(.panel-fade-leave-to) {
  opacity: 0;
  transform: scale(0.95);
}
</style>
