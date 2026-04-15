<template>
  <canvas
    ref="canvasRef"
    class="lissajous-orb"
    :class="{ transparent: !showBackground }"
  ></canvas>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'

// ----------------------------------------------------------------
// Props
// ----------------------------------------------------------------
interface Props {
  /** 当前对话状态，驱动动画模式 */
  dialogState: 'IDLE' | 'LISTENING' | 'PROCESSING' | 'ASKING' | 'EXECUTING' | 'FEEDBACK' | 'ERROR'
  /** 外部麦克风 AnalyserNode（录音时传入，null 时用演示/状态模拟） */
  micAnalyser?: AnalyserNode | null
  /** TTS 播放 AnalyserNode（AI 发声时传入，null 时用演示模拟） */
  ttsAnalyser?: AnalyserNode | null
  /** 最小半径占视口短边的比例 */
  minRadius?: number
  /** 最大半径占视口短边的比例 */
  maxRadius?: number
  /** 是否绘制深色背景 */
  showBackground?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  micAnalyser: null,
  ttsAnalyser: null,
  minRadius: 0.01,
  maxRadius: 0.20,
  showBackground: true,
})

// ----------------------------------------------------------------
// 固定参数（由用户定义：灵敏度1.20 / 拖尾强度1.3）
// ----------------------------------------------------------------
const SENSITIVITY  = 1.20
const TRAIL        = 1.30
const LINE_WEIGHT  = 1.00
const RING_GAP     = 0.060

// ----------------------------------------------------------------
// Canvas / RAF 引用
// ----------------------------------------------------------------
const canvasRef = ref<HTMLCanvasElement | null>(null)
let ctx: CanvasRenderingContext2D | null = null
let rafId = 0
let width  = 0
let height = 0
let dpr    = 1

// ----------------------------------------------------------------
// 音频平滑状态
// ----------------------------------------------------------------
let smoothedLevel = 0
let smoothedLow   = 0
let smoothedMid   = 0
let smoothedHigh  = 0
let hueDrift      = 190

// 频率数据缓冲（懒初始化）
let freqBuf: Uint8Array<ArrayBuffer> | null = null
let timeBuf: Uint8Array<ArrayBuffer> | null = null
let freqBufSize = 0

// ----------------------------------------------------------------
// 工具函数
// ----------------------------------------------------------------
function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v))
}
function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

// ----------------------------------------------------------------
// 音频指标
// ----------------------------------------------------------------
function ensureBufs(analyser: AnalyserNode): void {
  if (freqBufSize !== analyser.frequencyBinCount) {
    freqBuf = new Uint8Array(new ArrayBuffer(analyser.frequencyBinCount))
    timeBuf = new Uint8Array(new ArrayBuffer(analyser.fftSize))
    freqBufSize = analyser.frequencyBinCount
  }
}

function bandEnergy(_analyser: AnalyserNode, startRatio: number, endRatio: number): number {
  if (!freqBuf) return 0
  const start = Math.floor(freqBuf.length * startRatio)
  const end   = Math.max(start + 1, Math.floor(freqBuf.length * endRatio))
  let sum = 0
  for (let i = start; i < end; i++) sum += freqBuf[i]
  return sum / ((end - start) * 255)
}

function rmsLevel(analyser: AnalyserNode): number {
  if (!timeBuf) return 0
  analyser.getByteTimeDomainData(timeBuf)
  let sum = 0
  for (let i = 0; i < timeBuf.length; i++) {
    const n = (timeBuf[i] - 128) / 128
    sum += n * n
  }
  return Math.sqrt(sum / timeBuf.length)
}

function getAudioMetrics(t: number): { level: number; low: number; mid: number; high: number } {
  // 优先取当前活跃 analyser：AI 发声时用 tts，录音时用 mic
  const analyser = props.ttsAnalyser ?? props.micAnalyser

  if (analyser) {
    ensureBufs(analyser)
    analyser.getByteFrequencyData(freqBuf!)

    const level = clamp(rmsLevel(analyser) * SENSITIVITY, 0, 1)
    const low   = clamp(bandEnergy(analyser, 0.01, 0.07) * SENSITIVITY, 0, 1)
    const mid   = clamp(bandEnergy(analyser, 0.07, 0.24) * SENSITIVITY, 0, 1)
    const high  = clamp(bandEnergy(analyser, 0.24, 0.60) * SENSITIVITY, 0, 1)

    smoothedLevel = lerp(smoothedLevel, level, 0.22)
    smoothedLow   = lerp(smoothedLow,   low,   0.18)
    smoothedMid   = lerp(smoothedMid,   mid,   0.20)
    smoothedHigh  = lerp(smoothedHigh,  high,  0.26)
  } else {
    // 演示 / 状态驱动模拟
    const { dialogState } = props
    let talking = 0

    if (dialogState === 'LISTENING') {
      // 聆听：小幅呼吸，偶发微波动
      talking = Math.max(0, Math.sin(t * 1.2) * Math.sin(t * 0.4)) * 0.35
    } else if (dialogState === 'PROCESSING') {
      // 处理中：缓慢脉冲
      talking = 0.18 + 0.08 * Math.sin(t * 2.5)
    } else if (dialogState === 'ASKING') {
      // 反问：像说话一样有节奏
      talking = Math.max(0, Math.sin(t * 0.9) * Math.sin(t * 0.31)) * SENSITIVITY
    } else if (dialogState === 'EXECUTING') {
      // 执行中：稳定中等强度
      talking = 0.25 + 0.06 * Math.sin(t * 3.0)
    } else if (dialogState === 'FEEDBACK') {
      // 完成：温和呼吸
      talking = 0.12 + 0.04 * Math.sin(t * 1.5)
    } else if (dialogState === 'ERROR') {
      // 错误：急促短促抖动
      talking = 0.15 + 0.12 * Math.pow(Math.max(0, Math.sin(t * 6.0)), 3)
    } else {
      // IDLE：极小的"心跳"
      talking = 0.04 + 0.02 * Math.sin(t * 0.6)
    }

    const burst = 0.08 * Math.pow(Math.max(0, Math.sin(t * 4.1)), 10)
    smoothedLevel = lerp(smoothedLevel, clamp(talking * 0.55 + burst, 0, 1), 0.07)
    smoothedLow   = lerp(smoothedLow,   clamp(talking * 0.50 + 0.05, 0, 1), 0.05)
    smoothedMid   = lerp(smoothedMid,   clamp(talking * 0.55 + 0.05, 0, 1), 0.06)
    smoothedHigh  = lerp(smoothedHigh,  clamp(talking * 0.38 + burst * 0.5, 0, 1), 0.08)
  }

  return {
    level: clamp(smoothedLevel, 0, 1),
    low:   clamp(smoothedLow,   0, 1),
    mid:   clamp(smoothedMid,   0, 1),
    high:  clamp(smoothedHigh,  0, 1),
  }
}

// ----------------------------------------------------------------
// 绘制
// ----------------------------------------------------------------
const FREQ_PAIRS: [number, number][] = [[1,2],[2,3],[1,3],[2,3],[3,4],[1,2]]

interface Point { x: number; y: number }

function makePt(p: number, fx: number, fy: number, phase: number, sx: number, sy: number, ps: number): Point {
  return {
    x: sx * Math.sin(fx * p + phase + ps),
    y: sy * Math.cos(fy * p + ps * 0.6),
  }
}

function buildCurvePoints(count: number, builder: (p: number) => Point): Point[] {
  const pts: Point[] = []
  for (let i = 0; i < count; i++) {
    pts.push(builder((i / count) * Math.PI * 2))
  }
  return pts
}

function traceSmoothClosedCurve(pts: Point[]): void {
  if (!ctx || pts.length < 2) return
  ctx.beginPath()
  ctx.moveTo(pts[0].x, pts[0].y)
  for (let i = 0; i < pts.length; i++) {
    const p0 = pts[(i - 1 + pts.length) % pts.length]
    const p1 = pts[i]
    const p2 = pts[(i + 1) % pts.length]
    const p3 = pts[(i + 2) % pts.length]
    const cp1x = p1.x + (p2.x - p0.x) / 6
    const cp1y = p1.y + (p2.y - p0.y) / 6
    const cp2x = p2.x - (p3.x - p1.x) / 6
    const cp2y = p2.y - (p3.y - p1.y) / 6
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y)
  }
  ctx.closePath()
}

function drawPair(
  t: number, fx: number, fy: number, phase: number,
  radiusX: number, radiusY: number, alphaScale: number,
  metrics: ReturnType<typeof getAudioMetrics>, hueA: number, hueB: number
): void {
  if (!ctx) return
  const stableLevel = metrics.level * 0.6
  const stableLow   = metrics.low   * 0.65
  const stableHigh  = metrics.high  * 0.5
  const points      = 2400
  const PI          = Math.PI

  const layers = [
    { sx: radiusX * 1.04, sy: radiusY * 1.04, ps:  PI * 0.55, alpha: 0.07,  blur: 44, w: 7.2, hue: hueA,                pulse: 0.55 },
    { sx: radiusX * 1.01, sy: radiusY * 1.01, ps:  PI * 0.28, alpha: 0.10,  blur: 30, w: 4.2, hue: (hueA + 30) % 360,  pulse: 0.85 },
    { sx: radiusX,        sy: radiusY,         ps:  0,          alpha: 0.22,  blur: 18, w: 2.4, hue: hueB,               pulse: 1.20 },
    { sx: radiusX * 0.97, sy: radiusY * 0.97, ps: -PI * 0.28, alpha: 0.14,  blur: 10, w: 1.1, hue: (hueB + 20) % 360,  pulse: 1.55 },
  ]

  for (const l of layers) {
    const path = buildCurvePoints(points, (p) => makePt(p, fx, fy, phase, l.sx, l.sy, l.ps))
    traceSmoothClosedCurve(path)
    const widthPulse = 0.93 + 0.14 * (0.5 + 0.5 * Math.sin(t * (1.1 + l.pulse * 0.25) + l.ps * 1.7))
    ctx.lineWidth   = (l.w * widthPulse + stableLow * 1.4 + stableLevel * 2.2) * LINE_WEIGHT
    ctx.shadowBlur  = l.blur + stableLevel * 28
    ctx.shadowColor = `hsla(${l.hue}, 100%, 75%, ${(0.3 + stableHigh * 0.2) * alphaScale})`
    ctx.strokeStyle = `hsla(${l.hue}, 90%, 78%, ${l.alpha * alphaScale})`
    ctx.stroke()
  }

  const mainPath = buildCurvePoints(points, (p) => makePt(p, fx, fy, phase, radiusX, radiusY, 0))
  traceSmoothClosedCurve(mainPath)

  const grad = ctx.createLinearGradient(-radiusX, -radiusY, radiusX, radiusY)
  grad.addColorStop(0,    `hsla(${hueA},      100%, 80%, ${0.28 * alphaScale})`)
  grad.addColorStop(0.35, `hsla(${hueB},      100%, 72%, ${0.48 * alphaScale})`)
  grad.addColorStop(0.65, `hsla(${hueA + 20}, 100%, 88%, ${0.38 * alphaScale})`)
  grad.addColorStop(1,    `hsla(${hueB + 15}, 100%, 76%, ${0.28 * alphaScale})`)

  ctx.shadowBlur  = 28 + stableLevel * 36
  ctx.shadowColor = `hsla(${hueB}, 100%, 70%, ${(0.45 + stableLevel * 0.2) * alphaScale})`
  const mainWidthPulse = 0.95 + 0.12 * (0.5 + 0.5 * Math.sin(t * 1.45 + phase))
  ctx.lineWidth   = (1.25 * mainWidthPulse + stableLow * 1.7 + stableLevel * 2.6) * LINE_WEIGHT
  ctx.strokeStyle = grad
  ctx.stroke()

  ctx.globalCompositeOperation = 'lighter'
  ctx.lineWidth   = (0.62 + 0.18 * mainWidthPulse + stableHigh * 1.1) * LINE_WEIGHT
  ctx.shadowBlur  = 10 + stableHigh * 18
  ctx.strokeStyle = `hsla(${hueA}, 80%, 96%, ${(0.22 + stableLevel * 0.22) * alphaScale})`
  ctx.stroke()
  ctx.globalCompositeOperation = 'source-over'
}

function drawRing(
  t: number, ringR: number,
  stableLevel: number, stableHigh: number, _stableMid: number,
  hueA: number, hueB: number
): void {
  if (!ctx) return
  const breathe = 1 + 0.018 * Math.sin(t * 3.2) + stableLevel * 0.04

  ctx.beginPath()
  ctx.arc(0, 0, ringR * breathe * 1.06, 0, Math.PI * 2)
  ctx.lineWidth   = (6 + stableLevel * 10) * LINE_WEIGHT
  ctx.strokeStyle = `hsla(${hueA}, 100%, 70%, ${0.06 + stableLevel * 0.06})`
  ctx.shadowBlur  = 30 + stableLevel * 30
  ctx.shadowColor = `hsla(${hueA}, 100%, 72%, 0.4)`
  ctx.stroke()

  ctx.beginPath()
  ctx.arc(0, 0, ringR * breathe, 0, Math.PI * 2)
  ctx.lineWidth   = (1.2 + stableLevel * 1.5) * LINE_WEIGHT
  ctx.shadowBlur  = 12 + stableHigh * 18 + stableLevel * 20
  ctx.shadowColor = `hsla(${hueB}, 100%, 78%, 0.55)`

  const ringGrad = ctx.createConicGradient(t * 0.4, 0, 0)
  ringGrad.addColorStop(0,    `hsla(${hueA},      100%, 80%, ${0.5 + stableLevel * 0.3})`)
  ringGrad.addColorStop(0.25, `hsla(${hueB},      100%, 72%, ${0.4 + stableLevel * 0.2})`)
  ringGrad.addColorStop(0.5,  `hsla(${hueA + 20}, 100%, 88%, ${0.55 + stableLevel * 0.3})`)
  ringGrad.addColorStop(0.75, `hsla(${hueB + 15}, 100%, 74%, ${0.4 + stableLevel * 0.2})`)
  ringGrad.addColorStop(1,    `hsla(${hueA},      100%, 80%, ${0.5 + stableLevel * 0.3})`)
  ctx.strokeStyle = ringGrad
  ctx.stroke()

  ctx.globalCompositeOperation = 'lighter'
  ctx.beginPath()
  ctx.arc(0, 0, ringR * breathe, 0, Math.PI * 2)
  ctx.lineWidth   = 0.6 * LINE_WEIGHT
  ctx.shadowBlur  = 6
  ctx.strokeStyle = `hsla(${hueA}, 80%, 96%, ${0.18 + stableLevel * 0.2})`
  ctx.stroke()
  ctx.globalCompositeOperation = 'source-over'
}

function drawBackground(alpha: number): void {
  if (!ctx) return
  if (!props.showBackground) {
    ctx.clearRect(0, 0, width, height)
    return
  }
  ctx.fillStyle = `rgba(4, 6, 14, ${alpha})`
  ctx.fillRect(0, 0, width, height)
}

function drawFrame(now: number): void {
  if (!ctx) return
  const t       = now * 0.001
  const metrics = getAudioMetrics(t)

  const trailAlpha = (0.08 + (1 - clamp(metrics.level * 4, 0, 1)) * 0.18) / TRAIL
  drawBackground(trailAlpha)

  const stableLevel = metrics.level
  const stableMid   = metrics.mid
  const stableHigh  = metrics.high

  const minR   = Math.min(width, height) * props.minRadius
  const maxR   = Math.min(width, height) * props.maxRadius
  const expand = clamp(stableLevel * 2.2, 0, 1)
  const radius = minR + (maxR - minR) * Math.pow(expand, 1.8)

  const cycleT  = t / 20
  const pairIdx = Math.floor(cycleT) % FREQ_PAIRS.length
  const nextIdx = (pairIdx + 1) % FREQ_PAIRS.length
  const raw     = cycleT % 1
  const fade    = raw > 0.8 ? (raw - 0.8) / 0.2 : 0

  const [fxA, fyA] = FREQ_PAIRS[pairIdx]
  const [fxB, fyB] = FREQ_PAIRS[nextIdx]

  const phase = t * 0.15 + stableMid * 1.2 + stableLevel * 2.2

  hueDrift = 180 + 50 * (0.5 + 0.5 * Math.sin(t * 0.07 + stableHigh * 1.2))
  const hueA = hueDrift
  const hueB = (hueDrift + 60) % 360

  const baseSize = Math.min(width, height)
  const ringR    = radius + baseSize * RING_GAP
  const clipR    = ringR  * 0.96
  const drawR    = clipR

  ctx.save()
  ctx.translate(width * 0.5, height * 0.5)
  ctx.lineJoin = 'round'
  ctx.lineCap  = 'round'

  drawRing(t, ringR, stableLevel, stableHigh, stableMid, hueA, hueB)

  ctx.save()
  ctx.beginPath()
  ctx.arc(0, 0, clipR, 0, Math.PI * 2)
  ctx.clip()

  drawPair(t, fxA, fyA, phase, drawR, drawR, 1 - fade, metrics, hueA, hueB)
  if (fade > 0) {
    drawPair(t, fxB, fyB, phase, drawR, drawR, fade, metrics, hueA, hueB)
  }

  ctx.restore()
  ctx.restore()
}

// ----------------------------------------------------------------
// 生命周期
// ----------------------------------------------------------------
function resizeCanvas(): void {
  const el = canvasRef.value
  if (!el) return
  dpr    = Math.max(1, Math.min(window.devicePixelRatio || 1, 2))
  width  = el.clientWidth
  height = el.clientHeight
  el.width  = Math.floor(width  * dpr)
  el.height = Math.floor(height * dpr)
  ctx = el.getContext('2d')
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function animate(now: number): void {
  drawFrame(now)
  rafId = requestAnimationFrame(animate)
}

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  resizeCanvas()
  drawBackground(1)
  rafId = requestAnimationFrame(animate)

  resizeObserver = new ResizeObserver(() => {
    resizeCanvas()
  })
  if (canvasRef.value) {
    resizeObserver.observe(canvasRef.value)
  }
})

onUnmounted(() => {
  cancelAnimationFrame(rafId)
  resizeObserver?.disconnect()
})

// 切换状态时重置平滑值，避免残影跳变
watch(() => props.dialogState, () => {
  smoothedLevel = 0
  smoothedLow   = 0
  smoothedMid   = 0
  smoothedHigh  = 0
})
</script>

<style scoped>
.lissajous-orb {
  display: block;
  width: 100%;
  height: 100%;
  background:
    radial-gradient(circle at top,    rgba(28, 42, 84, 0.65), transparent 36%),
    radial-gradient(circle at bottom, rgba(17, 99, 110, 0.3), transparent 42%),
    #05070d;
}

.lissajous-orb.transparent {
  background: transparent;
}
</style>
