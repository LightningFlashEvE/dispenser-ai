/**
 * audio.ts  —  麦克风采集（AudioWorklet / ScriptProcessorNode 自动降级）+ TTS 播放队列
 *
 * 录音链路：
 *   安全上下文（HTTPS / localhost）：
 *     AudioContext(16kHz) → MediaStream → AudioWorkletNode(pcm-processor)
 *     如 AudioWorklet 不可用，则降级到 ScriptProcessorNode
 *   → 统一回调 → WS send(binary)
 *
 * 播放链路：
 *   enqueueBase64(base64, sampleRate) → AudioContext 解码 → 排队播放
 *   stopAll() → 立即中断所有播放并清空队列
 */

export type FrameCallback = (frame: ArrayBuffer) => void

/** 检查当前页面是否支持麦克风 API（HTTPS / localhost 下才可用） */
export function isMicAvailable(): boolean {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)
}

/** 获取麦克风不可用的原因提示（仅在不支持时调用） */
export function getMicUnavailableReason(): string | null {
  if (isMicAvailable()) return null
  if (!window.isSecureContext) {
    return '麦克风需要 HTTPS 环境或 localhost 访问。当前地址为 ' + location.href
  }
  return '当前浏览器不支持麦克风功能'
}

export type MicErrorCode =
  | 'NotAllowedError'
  | 'NotFoundError'
  | 'NotReadableError'
  | 'SecurityError'
  | 'ConnectionError'
  | 'UnknownError'

export interface MicError {
  code: MicErrorCode
  message: string
}

function isLocalhost(): boolean {
  return ['localhost', '127.0.0.1', '::1'].includes(location.hostname)
}

function insecureContextMessage(): string {
  if (isLocalhost()) {
    return '当前浏览器未把本机页面识别为安全上下文，请改用 http://localhost:5173 或 https://localhost:5173'
  }
  return `当前页面是 ${location.protocol}//${location.host}，浏览器禁止 HTTP 局域网页面使用麦克风。请用启动脚本输出的 HTTPS 局域网地址访问。`
}

function micErrorMessage(e: unknown): MicError {
  const err = e as DOMException
  if (err.name === 'NotAllowedError') {
    return { code: 'NotAllowedError', message: '请允许麦克风权限后才能使用语音功能' }
  }
  if (err.name === 'NotFoundError') {
    return { code: 'NotFoundError', message: '未找到麦克风设备，请检查是否已连接' }
  }
  if (err.name === 'NotReadableError') {
    return { code: 'NotReadableError', message: '麦克风被其他程序占用，请关闭其他使用麦克风的应用' }
  }
  if (err.name === 'SecurityError') {
    return { code: 'SecurityError', message: insecureContextMessage() }
  }
  return { code: 'UnknownError', message: err.message || '麦克风初始化失败' }
}

// ─────────────────────────────────────────────────────────────────
//  AudioRecorder — 支持 AudioWorklet 和 ScriptProcessorNode 两种模式
// ─────────────────────────────────────────────────────────────────

export class AudioRecorder {
  private ctx: AudioContext | null = null
  private worklet: AudioWorkletNode | null = null
  private processor: ScriptProcessorNode | null = null
  private silentSink: GainNode | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private stream: MediaStream | null = null
  private _paused = true
  private _onFrame: FrameCallback | null = null

  get isRecording(): boolean {
    return !this._paused && this.stream !== null
  }

  async init(onFrame: FrameCallback): Promise<void> {
    if (this.ctx) {
      this._onFrame = onFrame
      return
    }
    this._onFrame = onFrame
    this.ctx = new AudioContext({ sampleRate: 16000 })
    this.silentSink = this.ctx.createGain()
    this.silentSink.gain.value = 0
    this.silentSink.connect(this.ctx.destination)

    if (this.ctx.audioWorklet) {
      // 安全上下文（HTTPS / localhost）：优先使用 AudioWorklet
      await this.ctx.audioWorklet.addModule('/worklets/pcm-processor.js')
      this.worklet = new AudioWorkletNode(this.ctx, 'pcm-processor')
      this.worklet.port.onmessage = (evt: MessageEvent<ArrayBuffer>) => {
        if (!this._paused && this._onFrame) this._onFrame(evt.data)
      }
    } else {
      // AudioWorklet 不可用时降级为 ScriptProcessorNode
      // 512 样本 ≈ 32ms @ 16kHz，对语音识别完全够用
      this.processor = this.ctx.createScriptProcessor(512, 1, 1)
      this.processor.onaudioprocess = (evt: AudioProcessingEvent) => {
        if (this._paused || !this._onFrame) return
        const input = evt.inputBuffer.getChannelData(0)
        const int16 = new Int16Array(input.length)
        for (let j = 0; j < input.length; j++) {
          const s = Math.max(-1, Math.min(1, input[j]))
          int16[j] = Math.round(s < 0 ? s * 32768 : s * 32767)
        }
        this._onFrame(int16.buffer)
      }
    }
  }

  /**
   * 启动录音。
   * 返回 ok=true 表示成功，ok=false 表示失败，error 包含错误信息。
   */
  async startRecording(): Promise<{ ok: true } | { ok: false; error: MicError }> {
    if (!this.ctx) {
      return { ok: false, error: { code: 'UnknownError', message: '录音器未初始化，请先调用 init()' } }
    }

    if (!window.isSecureContext) {
      return { ok: false, error: {
        code: 'SecurityError' as MicErrorCode,
        message: insecureContextMessage(),
      }}
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      if (location.protocol !== 'https:' && !isLocalhost()) {
        return { ok: false, error: {
          code: 'SecurityError' as MicErrorCode,
          message: insecureContextMessage(),
        }}
      }
      return { ok: false, error: {
        code: 'NotFoundError' as MicErrorCode,
        message: '当前浏览器不支持麦克风功能，请尝试使用 Chrome 或 Edge',
      }}
    }

    if (this.ctx.state === 'suspended') await this.ctx.resume()
    if (this.stream) this.stopRecording()

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
    } catch (e) {
      return { ok: false, error: micErrorMessage(e) }
    }

    this.source = this.ctx.createMediaStreamSource(this.stream)

    if (this.worklet) {
      this.source.connect(this.worklet)
      if (this.silentSink) this.worklet.connect(this.silentSink)
      this.worklet.port.postMessage('start')
    } else if (this.processor) {
      this.source.connect(this.processor)
      if (this.silentSink) this.processor.connect(this.silentSink)
    } else {
      return { ok: false, error: { code: 'UnknownError', message: '音频处理管线未初始化' } }
    }

    this._paused = false
    return { ok: true }
  }

  stopRecording(): void {
    if (!this.stream) return
    this._paused = true

    if (this.worklet) {
      this.worklet.port.postMessage('stop')
    }

    this.source?.disconnect()
    this._disconnectNode(this.worklet)
    this._disconnectNode(this.processor)
    this.source = null
    this.stream.getTracks().forEach((t) => t.stop())
    this.stream = null
  }

  dispose(): void {
    this.stopRecording()
    this._disconnectNode(this.worklet)
    this.worklet = null
    this._disconnectNode(this.processor)
    this.processor = null
    this._disconnectNode(this.silentSink)
    this.silentSink = null
    this.ctx?.close()
    this.ctx = null
    this._onFrame = null
  }

  private _disconnectNode(node: AudioNode | null): void {
    try { node?.disconnect() } catch { /* already disconnected */ }
  }
}

// ─────────────────────────────────────────────────────────────────
//  AudioPlayer  —  接收 tts.chunk 后按序播放
// ─────────────────────────────────────────────────────────────────

interface PlayItem {
  pcm: Float32Array
  sampleRate: number
}

export class AudioPlayer {
  private ctx: AudioContext | null = null
  private queue: PlayItem[] = []
  private currentSource: AudioBufferSourceNode | null = null
  private _playing = false

  private _ensureCtx(sampleRate: number): AudioContext {
    if (!this.ctx || this.ctx.state === 'closed') {
      this.ctx = new AudioContext({ sampleRate })
    }
    return this.ctx
  }

  enqueueBase64(base64: string, sampleRate: number): void {
    const pcm = _base64ToPcmFloat32(base64)
    this.queue.push({ pcm, sampleRate })
    if (!this._playing) void this._playNext()
  }

  private async _playNext(): Promise<void> {
    if (this.queue.length === 0) {
      this._playing = false
      return
    }
    this._playing = true
    const { pcm, sampleRate } = this.queue.shift()!

    const ctx = this._ensureCtx(sampleRate)
    if (ctx.state === 'suspended') await ctx.resume()

    const processed = _removeTailFadeOut(pcm, sampleRate)

    const audioBuffer = ctx.createBuffer(1, processed.length, sampleRate)
    audioBuffer.getChannelData(0).set(processed)

    const src = ctx.createBufferSource()
    src.buffer = audioBuffer
    src.connect(ctx.destination)
    src.onended = () => {
      this.currentSource = null
      void this._playNext()
    }
    this.currentSource = src
    src.start()
  }

  stopAll(): void {
    this.queue = []
    this._playing = false
    try { this.currentSource?.stop() } catch { /* already stopped */ }
    this.currentSource = null
  }

  get isPlaying(): boolean {
    return this._playing
  }

  dispose(): void {
    this.stopAll()
    this.ctx?.close()
    this.ctx = null
  }
}

// ─────────────────────────────────────────────────────────────────
//  工具函数
// ─────────────────────────────────────────────────────────────────

/**
 * 去除音频末尾 fade-out（渐弱）。
 */
function _removeTailFadeOut(pcm: Float32Array, sampleRate: number): Float32Array {
  const fadeMs = 80
  const fadeSamples = Math.floor((fadeMs / 1000) * sampleRate)
  if (pcm.length < fadeSamples * 2) return pcm

  const startIdx = pcm.length - fadeSamples
  const quarter = Math.floor(fadeSamples / 4)

  const startRms = _rms(pcm, startIdx, startIdx + quarter)
  const endRms = _rms(pcm, pcm.length - quarter, pcm.length)

  if (startRms > 0.001 && endRms / startRms < 0.6) {
    const result = new Float32Array(pcm)
    for (let i = startIdx; i < result.length; i++) {
      const t = (i - startIdx) / fadeSamples // 0 → 1
      const gain = 1.0 + t * 0.6 // 线性补偿到 1.6 倍
      result[i] = Math.max(-1.0, Math.min(1.0, result[i] * gain))
    }
    return result
  }
  return pcm
}

function _rms(pcm: Float32Array, start: number, end: number): number {
  let sum = 0
  const s = Math.max(0, start)
  const e = Math.min(pcm.length, end)
  for (let i = s; i < e; i++) sum += pcm[i] * pcm[i]
  return Math.sqrt(sum / (e - s))
}

function _base64ToPcmFloat32(base64: string): Float32Array {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  const int16 = new Int16Array(bytes.buffer)
  const float32 = new Float32Array(int16.length)
  for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768
  return float32
}
