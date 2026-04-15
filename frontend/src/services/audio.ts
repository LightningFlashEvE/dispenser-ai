/**
 * audio.ts — 麦克风录音 + TTS 音频播放封装
 *
 * 对外暴露：
 *   startRecording()  / stopRecording()  — 麦克风采集，向后端推 PCM
 *   playTtsAudio()                       — 播放后端推送的 TTS PCM 数据
 *   getMicAnalyser()                     — 供 LissajousOrb 实时读取麦克风频谱
 *   getTtsAnalyser()                     — 供 LissajousOrb 实时读取 TTS 频谱
 */

import { sendAudioChunk, sendJson } from './websocket'

// ─── 麦克风录音状态 ───────────────────────────────────────────────
let micStream: MediaStream | null         = null
let micAudioCtx: AudioContext | null      = null
let micProcessor: ScriptProcessorNode | null = null
let micAnalyserNode: AnalyserNode | null  = null

// ─── TTS 播放状态 ─────────────────────────────────────────────────
let ttsAudioCtx: AudioContext | null      = null
let ttsAnalyserNode: AnalyserNode | null  = null
/** 当前正在排队的 TTS 播放结束时间（AudioContext time，秒） */
let ttsScheduledUntil = 0

// ─── 公开的 getter（响应式 computed 轮询用） ──────────────────────
export function getMicAnalyser(): AnalyserNode | null {
  return micAnalyserNode
}

export function getTtsAnalyser(): AnalyserNode | null {
  return ttsAnalyserNode
}

// ─── 麦克风录音 ───────────────────────────────────────────────────

export async function startRecording(): Promise<void> {
  micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })

  micAudioCtx = new AudioContext({ sampleRate: 16000 })

  const source = micAudioCtx.createMediaStreamSource(micStream)

  // 分析节点：供 LissajousOrb 读取麦克风频谱
  micAnalyserNode = micAudioCtx.createAnalyser()
  micAnalyserNode.fftSize = 2048
  micAnalyserNode.smoothingTimeConstant = 0.72

  micProcessor = micAudioCtx.createScriptProcessor(4096, 1, 1)

  micProcessor.onaudioprocess = (e: AudioProcessingEvent) => {
    const float32 = e.inputBuffer.getChannelData(0)
    const int16   = float32ToInt16(float32)
    sendAudioChunk(int16.buffer as ArrayBuffer)
  }

  source.connect(micAnalyserNode)
  micAnalyserNode.connect(micProcessor)
  micProcessor.connect(micAudioCtx.destination)
}

export function stopRecording(): void {
  micProcessor?.disconnect()
  micAnalyserNode?.disconnect()
  micAudioCtx?.close()
  micStream?.getTracks().forEach((t) => t.stop())

  micProcessor    = null
  micAnalyserNode = null
  micAudioCtx     = null
  micStream       = null

  sendJson({ type: 'audio_end' })
}

export function cancelDialog(): void {
  stopRecording()
  sendJson({ type: 'cancel' })
}

// ─── TTS 音频播放 ─────────────────────────────────────────────────
/**
 * 播放后端通过 WebSocket tts_audio 消息推送的 PCM 数据。
 *
 * 后端格式约定（待确认后调整解码逻辑）：
 *   payload.data   — Base64 编码的原始 PCM（Int16 LE，单声道）
 *   payload.sample_rate — 采样率（Hz，默认 22050）
 *
 * 在格式确认前，此函数以 Int16 LE / 单声道 / 22050Hz 为默认值解码。
 * 若后端改为 Float32 或 WAV 容器，只需修改此函数内部解码部分。
 */
export function playTtsAudio(base64Pcm: string, sampleRate = 22050): void {
  if (!ttsAudioCtx) {
    ttsAudioCtx = new AudioContext({ sampleRate })

    // 分析节点：供 LissajousOrb 读取 TTS 频谱
    ttsAnalyserNode = ttsAudioCtx.createAnalyser()
    ttsAnalyserNode.fftSize = 2048
    ttsAnalyserNode.smoothingTimeConstant = 0.72
    ttsAnalyserNode.connect(ttsAudioCtx.destination)

    ttsScheduledUntil = 0
  }

  // Base64 → Int16 PCM → Float32
  const binary  = atob(base64Pcm)
  const bytes   = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)

  const int16   = new Int16Array(bytes.buffer)
  const float32 = new Float32Array(int16.length)
  for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768.0

  const buffer = ttsAudioCtx.createBuffer(1, float32.length, sampleRate)
  buffer.copyToChannel(float32, 0)

  const source = ttsAudioCtx.createBufferSource()
  source.buffer = buffer
  source.connect(ttsAnalyserNode!)

  // 串行排队播放（避免多段 TTS chunk 重叠）
  const now       = ttsAudioCtx.currentTime
  const startAt   = Math.max(now, ttsScheduledUntil)
  source.start(startAt)
  ttsScheduledUntil = startAt + buffer.duration
}

/**
 * 停止所有 TTS 播放，释放 TTS AudioContext。
 * 后端 state_change → IDLE/LISTENING 时调用。
 */
export function stopTtsPlayback(): void {
  ttsAudioCtx?.close()
  ttsAudioCtx     = null
  ttsAnalyserNode = null
  ttsScheduledUntil = 0
}

// ─── 内部工具 ─────────────────────────────────────────────────────
function float32ToInt16(buffer: Float32Array): Int16Array {
  const out = new Int16Array(buffer.length)
  for (let i = 0; i < buffer.length; i++) {
    const s = Math.max(-1, Math.min(1, buffer[i]))
    out[i]  = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out
}
