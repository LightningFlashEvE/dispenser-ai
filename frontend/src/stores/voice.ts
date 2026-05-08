import { defineStore } from 'pinia'
import { ref, computed, shallowRef, triggerRef } from 'vue'
import { VoiceWebSocket, type InboundMsg, type SessionState, type PendingPayload, type DraftPayload, type Correction, type Suggestion } from '@/services/websocket'
import { AudioRecorder, AudioPlayer, type MicError } from '@/services/audio'

export type MsgRole = 'user' | 'assistant' | 'system'

export interface AsrMeta {
  rawText: string
  normalizedText: string
  confidence: number | null
  corrections: Correction[]
  suggestions: Suggestion[]
  needsConfirmation: boolean
}

export interface ChatMessage {
  id: string; role: MsgRole; text: string; timestamp: string
  isStreaming?: boolean; isError?: boolean
  asrMeta?: AsrMeta
}

export interface BalanceSeriesPoint {
  ts: number
  value: number
}

const BALANCE_DISPLAY_FLUSH_MS = 500
const BALANCE_SERIES_FLUSH_MS = 500
const BALANCE_SERIES_WINDOW_MS = 10_000
const BALANCE_SERIES_MAX_POINTS = 1_000

export const useVoiceStore = defineStore('voice', () => {
  const sessionState = ref<SessionState>('idle')
  const messages = ref<ChatMessage[]>([])
  const asrPartial = ref('')
  const pendingIntent = ref<PendingPayload | null>(null)
  const currentDraft = ref<DraftPayload | null>(null)
  const isConnected = ref(false)
  const errorMsg = ref<string | null>(null)
  const asrMeta = ref<AsrMeta | null>(null)
  const balanceMg = ref<number | null>(null)
  const balanceStable = ref(false)
  const balanceOverLimit = ref(false)
  const balanceLatestMg = ref<number | null>(null)
  const balanceLatestStable = ref(false)
  const balanceLatestOverLimit = ref(false)
  const balanceSeriesPoints = shallowRef<BalanceSeriesPoint[]>([])
  const balanceSeriesVersion = ref(0)
  const audioInited = ref(false)
  const audioError = ref<string | null>(null)
  const micError = ref<MicError | null>(null)
  const currentSessionId = ref<string | null>(null)
  const isRecording = ref(false)
  const micLevel = ref(0)

  const _ws = new VoiceWebSocket()
  const _recorder = new AudioRecorder()
  const _player = new AudioPlayer()
  let _streamingId: string | null = null
  let _balanceFlushTimer: ReturnType<typeof setTimeout> | null = null
  let _balanceSeriesFlushTimer: ReturnType<typeof setTimeout> | null = null
  let _balanceCooldownUntil = 0
  let _balanceSeriesCooldownUntil = 0

  const isPlaying = computed(() => _player.isPlaying)

  function _flushBalanceDisplay(): void {
    balanceMg.value = balanceLatestMg.value
    balanceStable.value = balanceLatestStable.value
    balanceOverLimit.value = balanceLatestOverLimit.value
  }

  function _scheduleBalanceFlush(): void {
    const now = Date.now()
    if (now >= _balanceCooldownUntil) {
      _flushBalanceDisplay()
      _balanceCooldownUntil = now + BALANCE_DISPLAY_FLUSH_MS
      if (_balanceFlushTimer) {
        clearTimeout(_balanceFlushTimer)
        _balanceFlushTimer = null
      }
      _balanceFlushTimer = setTimeout(() => {
        _balanceFlushTimer = null
        if (
          balanceMg.value !== balanceLatestMg.value ||
          balanceStable.value !== balanceLatestStable.value ||
          balanceOverLimit.value !== balanceLatestOverLimit.value
        ) {
          _flushBalanceDisplay()
          _balanceCooldownUntil = Date.now() + BALANCE_DISPLAY_FLUSH_MS
        }
      }, BALANCE_DISPLAY_FLUSH_MS)
      return
    }

    if (_balanceFlushTimer) return
    _balanceFlushTimer = setTimeout(() => {
      _balanceFlushTimer = null
      _flushBalanceDisplay()
      _balanceCooldownUntil = Date.now() + BALANCE_DISPLAY_FLUSH_MS
    }, Math.max(0, _balanceCooldownUntil - now))
  }

  function _parseBalanceTimestamp(timestamp?: string): number {
    if (!timestamp) return Date.now()
    const parsed = Date.parse(timestamp)
    return Number.isFinite(parsed) ? parsed : Date.now()
  }

  function _publishBalanceSeries(): void {
    triggerRef(balanceSeriesPoints)
    balanceSeriesVersion.value += 1
  }

  function _scheduleBalanceSeriesFlush(): void {
    const now = Date.now()
    if (now >= _balanceSeriesCooldownUntil) {
      _publishBalanceSeries()
      _balanceSeriesCooldownUntil = now + BALANCE_SERIES_FLUSH_MS
      if (_balanceSeriesFlushTimer) {
        clearTimeout(_balanceSeriesFlushTimer)
        _balanceSeriesFlushTimer = null
      }
      return
    }

    if (_balanceSeriesFlushTimer) return
    _balanceSeriesFlushTimer = setTimeout(() => {
      _balanceSeriesFlushTimer = null
      _publishBalanceSeries()
      _balanceSeriesCooldownUntil = Date.now() + BALANCE_SERIES_FLUSH_MS
    }, Math.max(0, _balanceSeriesCooldownUntil - now))
  }

  function _appendBalanceSeriesPoint(value: number, timestamp?: string): void {
    const ts = _parseBalanceTimestamp(timestamp)
    const minTs = ts - BALANCE_SERIES_WINDOW_MS
    const points = balanceSeriesPoints.value
    points.push({ ts, value })
    while (points.length > 0 && points[0].ts < minTs) points.shift()
    if (points.length > BALANCE_SERIES_MAX_POINTS) {
      points.splice(0, points.length - BALANCE_SERIES_MAX_POINTS)
    }
    _scheduleBalanceSeriesFlush()
  }

  const stateLabel = computed<string>(() => {
    const map: Record<string, string> = {
      idle: '待机', listening: '聆听中', recognizing: '识别中', thinking: '思考中',
      speaking: '回复中', awaiting_confirmation: '等待确认', interrupted: '已打断',
      IDLE: '待机', LISTENING: '聆听中', PROCESSING: '处理中',
      ASKING: '反问中', EXECUTING: '执行中', FEEDBACK: '反馈中', ERROR: '错误',
    }
    return map[sessionState.value] ?? sessionState.value
  })

  function connect(sessionId?: string): void {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    let url = `${proto}//${location.host}/ws/voice`
    if (sessionId) {
      url += `?session_id=${encodeURIComponent(sessionId)}`
    }
    _ws.connect(url, _onMessage, (connected) => {
      isConnected.value = connected
      if (!connected) {
        isRecording.value = false
        micLevel.value = 0
        sessionState.value = 'idle'
      }
    })
  }

  function disconnect(): void {
    _ws.disconnect()
    _recorder.stopRecording()
    isRecording.value = false
    micLevel.value = 0
    _player.dispose()
    if (_balanceFlushTimer) {
      clearTimeout(_balanceFlushTimer)
      _balanceFlushTimer = null
    }
    if (_balanceSeriesFlushTimer) {
      clearTimeout(_balanceSeriesFlushTimer)
      _balanceSeriesFlushTimer = null
    }
    _balanceCooldownUntil = 0
    _balanceSeriesCooldownUntil = 0
  }

  function switchSession(sessionId: string): void {
    if (_recorder.isRecording) {
      _recorder.stopRecording()
      isRecording.value = false
      micLevel.value = 0
    }
    _player.stopAll()
    currentSessionId.value = sessionId
    _ws.reconnectWithSession(sessionId)
  }

  function loadHistory(historyMessages: Array<{ role: string; content: string }>): void {
    messages.value = historyMessages.map((m) => ({
      id: `hist_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      role: m.role as 'user' | 'assistant',
      text: m.content,
      timestamp: new Date().toISOString(),
    }))
    _streamingId = null
  }

  function _onMessage(msg: InboundMsg): void {
    if (msg.type === 'state_change') {
      sessionState.value = ((msg as { state: string }).state?.toLowerCase?.() ?? 'idle') as SessionState
      return
    }
    if (msg.type === 'stt_final') {
      asrPartial.value = ''
      if (!messages.value.some((m) => m.role === 'user' && m.text === (msg as { text: string }).text))
        _addMsg('user', (msg as { text: string }).text)
      return
    }
    switch (msg.type) {
      case 'connected': break
      case 'state.update':
        sessionState.value = msg.state
        if (msg.state === 'idle' || msg.state === 'IDLE') asrPartial.value = ''
        break
      case 'asr.partial': asrPartial.value = msg.text; break
      case 'asr.final':
        asrPartial.value = ''
        // 提取 ASR 纠错元数据（新后端返回）
        if (msg.raw_text && msg.normalized_text) {
          asrMeta.value = {
            rawText: msg.raw_text,
            normalizedText: msg.normalized_text,
            confidence: null,
            corrections: msg.corrections || [],
            suggestions: msg.suggestions || [],
            needsConfirmation: msg.needs_confirmation || false,
          }
        } else {
          asrMeta.value = null
        }
        if (!messages.value.some((m) => m.role === 'user' && m.text === msg.text))
          _addMsg('user', msg.text, undefined, false, asrMeta.value ?? undefined)
        break
      case 'user_message':
        if (!messages.value.some((m) => m.role === 'user' && m.text === msg.text))
          _addMsg('user', msg.text, msg.timestamp)
        break
      case 'chat.delta':
        if (!_streamingId) {
          const id = `ai_${Date.now()}`; _streamingId = id
          messages.value.push({ id, role: 'assistant', text: msg.text, timestamp: new Date().toISOString(), isStreaming: true })
        } else {
          const idx = messages.value.findIndex((m) => m.id === _streamingId)
          if (idx !== -1) messages.value[idx].text += msg.text
        }
        break
      case 'chat.done':
        if (_streamingId) {
          const idx = messages.value.findIndex((m) => m.id === _streamingId)
          if (idx !== -1) { messages.value[idx].text = msg.text; messages.value[idx].isStreaming = false }
          _streamingId = null
        } else if (msg.text) {
          _addMsg('assistant', msg.text)
        }
        break
      case 'dialog_reply': if (!_streamingId) _addMsg('assistant', (msg as { text: string }).text); break
      case 'question': break
      case 'tts.chunk': _player.enqueueBase64(msg.data, msg.sample_rate); break
      case 'tts.done': break
      case 'tts_end': _player.stopAll(); break
      case 'pending_intent': pendingIntent.value = msg.data; break
      case 'draft_update':
        currentDraft.value = msg.data
        if (msg.data.status === 'CANCELLED') currentDraft.value = msg.data
        break
      case 'pending_cleared': pendingIntent.value = null; break
      case 'slot_filling': break
      case 'command_sent':
        currentDraft.value = null
        pendingIntent.value = null
        _addMsg('system', `✓ 指令已下发  [${msg.command_id.slice(-8)}]`)
        break
      case 'command_result': {
        const d = msg.data; const ok = d.status === 'completed'
        _addMsg('system', ok ? '✓ 执行完成' : `✗ 执行${d.status}${d.message ? '：' + d.message : ''}`, undefined, !ok)
        break
      }
      case 'balance_reading':
        balanceLatestMg.value = msg.value_mg
        balanceLatestStable.value = msg.stable
        balanceLatestOverLimit.value = false
        _appendBalanceSeriesPoint(msg.value_mg, msg.timestamp)
        _scheduleBalanceFlush()
        break
      case 'balance_over_limit':
        balanceLatestMg.value = msg.value_mg
        balanceLatestStable.value = false
        balanceLatestOverLimit.value = true
        _appendBalanceSeriesPoint(msg.value_mg, msg.timestamp)
        _scheduleBalanceFlush()
        break
      case 'error':
        errorMsg.value = msg.message; setTimeout(() => { errorMsg.value = null }, 5000); break
      case 'ping': break
    }
  }

  function _addMsg(role: MsgRole, text: string, timestamp?: string, isError = false, meta?: AsrMeta): void {
    messages.value.push({
      id: `${role}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      role, text, timestamp: timestamp ?? new Date().toISOString(), isError,
      asrMeta: meta,
    })
  }

  async function initAudio(): Promise<void> {
    if (audioInited.value) return
    try {
      await _recorder.init((frame: ArrayBuffer) => {
        micLevel.value = calcMicLevel(frame)
        _ws.sendAudioFrame(frame)
      })
      audioInited.value = true
      audioError.value = null
      micError.value = null
    } catch (e) {
      audioError.value = e instanceof Error ? e.message : '麦克风初始化失败'
      throw e
    }
  }

  async function startRecording(): Promise<void> {
    micError.value = null
    if (!isConnected.value) {
      micError.value = {
        code: 'ConnectionError',
        message: '语音服务未连接，请稍等连接恢复后再开始对话',
      }
      return
    }
    if (!audioInited.value) await initAudio()
    _player.stopAll()
    _ws.bargeIn()
    const result = await _recorder.startRecording()
    if (!result.ok) {
      isRecording.value = false
      micLevel.value = 0
      micError.value = result.error
      return
    }
    isRecording.value = true
  }

  function stopRecording(): void {
    _recorder.stopRecording()
    isRecording.value = false
    micLevel.value = 0
    if (!isConnected.value) {
      micError.value = {
        code: 'ConnectionError',
        message: '语音服务连接已断开，本次录音未发送，请连接恢复后重试',
      }
      return
    }
    _ws.commitAudio()
  }

  function sendText(text: string): void {
    const t = text.trim()
    if (!t) return

    const ok = _ws.sendUserText(t)
    if (!ok) {
      errorMsg.value = '语音服务连接已断开，请稍后重试'
      setTimeout(() => { errorMsg.value = null }, 5000)
      return
    }

    _addMsg('user', t)
  }
  function confirmDraft(): void { sendText('确认') }
  function cancelDraft(): void { _ws.cancelTask() }
  function confirm(): void { pendingIntent.value = null; _ws.confirm() }
  function cancelPending(): void { pendingIntent.value = null; _ws.cancelPending() }
  function cancelTask(): void { _ws.cancelTask() }
  function clearMessages(): void { messages.value = []; _streamingId = null; asrPartial.value = ''; pendingIntent.value = null; currentDraft.value = null }
  function clearMicError(): void { micError.value = null }

  function calcMicLevel(frame: ArrayBuffer): number {
    const samples = new Int16Array(frame)
    if (samples.length === 0) return 0

    let sum = 0
    for (let i = 0; i < samples.length; i += 1) {
      const normalized = samples[i] / 32768
      sum += normalized * normalized
    }

    const rms = Math.sqrt(sum / samples.length)
    const boosted = Math.min(1, rms * 8)
    return Math.pow(boosted, 0.65)
  }

  return {
    sessionState, messages, asrPartial, pendingIntent, currentDraft, isConnected, errorMsg,
    balanceMg, balanceStable, balanceOverLimit, balanceSeriesPoints, balanceSeriesVersion, audioInited, audioError,
    isRecording, isPlaying, stateLabel, micLevel,
    currentSessionId, micError,
    connect, disconnect, switchSession, loadHistory, initAudio, startRecording, stopRecording,
    sendText, confirmDraft, cancelDraft, confirm, cancelPending, cancelTask, clearMessages, clearMicError,
  }
})
