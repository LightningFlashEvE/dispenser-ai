<template>
  <div class="lissajous-container" ref="container">
    <canvas ref="canvasEl"></canvas>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps<{
  isActive: boolean
}>()

const container = ref<HTMLElement | null>(null)
const canvasEl = ref<HTMLCanvasElement | null>(null)

let ctx: CanvasRenderingContext2D | null = null
let animationFrameId = 0
let width = 0
let height = 0
let dpr = 1
let resizeObserver: ResizeObserver | null = null

let smoothedLevel = 0
let smoothedLow = 0
let smoothedMid = 0
let smoothedHigh = 0
let hueDrift = 190

interface AudioMetrics {
  level: number
  low: number
  mid: number
  high: number
}

const params = {
  sensitivity: 1,
  minRadius: 0.12,
  maxRadius: 0.35,
  lineWeight: 1,
  ringGap: 0.08,
  trail: 1,
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

function getAudioMetrics(t: number): AudioMetrics {
  if (props.isActive) {
    const talking = Math.max(0, Math.sin(t * 1.5) * Math.sin(t * 0.5)) * params.sensitivity
    const burst   = 0.08 * Math.pow(Math.max(0, Math.sin(t * 6.1)), 10)
    smoothedLevel = lerp(smoothedLevel, clamp(talking * 0.55 + burst, 0, 1), 0.07)
    smoothedLow = lerp(smoothedLow, clamp(talking * 0.5 + 0.05, 0, 1), 0.05)
    smoothedMid = lerp(smoothedMid, clamp(talking * 0.55 + 0.05, 0, 1), 0.06)
    smoothedHigh = lerp(smoothedHigh, clamp(talking * 0.38 + burst * 0.5, 0, 1), 0.08)
  } else {
    smoothedLevel = lerp(smoothedLevel, 0.01, 0.05)
    smoothedLow = lerp(smoothedLow, 0.05, 0.05)
    smoothedMid = lerp(smoothedMid, 0.05, 0.05)
    smoothedHigh = lerp(smoothedHigh, 0.01, 0.05)
  }

  return {
    level: clamp(smoothedLevel, 0, 1),
    low: clamp(smoothedLow, 0, 1),
    mid: clamp(smoothedMid, 0, 1),
    high: clamp(smoothedHigh, 0, 1),
  }
}

function drawBackground(alpha: number) {
  if (!ctx) return
  ctx.globalCompositeOperation = 'destination-out'
  ctx.fillStyle = `rgba(0, 0, 0, ${alpha})`
  ctx.fillRect(0, 0, width, height)
  ctx.globalCompositeOperation = 'source-over'
}

function buildCurvePoints(points: number, pointBuilder: (p: number) => { x: number, y: number }) {
  const pathPoints = []
  for (let i = 0; i < points; i += 1) {
    const p = (i / points) * Math.PI * 2
    pathPoints.push(pointBuilder(p))
  }
  return pathPoints
}

function traceSmoothClosedCurve(pathPoints: {x: number, y: number}[]) {
  if (!ctx || pathPoints.length < 2) return

  ctx.beginPath()
  ctx.moveTo(pathPoints[0].x, pathPoints[0].y)

  for (let i = 0; i < pathPoints.length; i += 1) {
    const p0 = pathPoints[(i - 1 + pathPoints.length) % pathPoints.length]
    const p1 = pathPoints[i]
    const p2 = pathPoints[(i + 1) % pathPoints.length]
    const p3 = pathPoints[(i + 2) % pathPoints.length]

    const cp1x = p1.x + (p2.x - p0.x) / 6
    const cp1y = p1.y + (p2.y - p0.y) / 6
    const cp2x = p2.x - (p3.x - p1.x) / 6
    const cp2y = p2.y - (p3.y - p1.y) / 6

    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y)
  }
  ctx.closePath()
}

const FREQ_PAIRS = [[1,2],[2,3],[1,3],[2,3],[3,4],[1,2]]

function makePt(p: number, fx: number, fy: number, phase: number, sx: number, sy: number, ps: number) {
  return {
    x: sx * Math.sin(fx * p + phase + ps),
    y: sy * Math.cos(fy * p + ps * 0.6),
  }
}

function drawPair(t: number, fx: number, fy: number, phase: number, radiusX: number, radiusY: number, alphaScale: number, metrics: AudioMetrics, hueA: number, hueB: number) {
  if (!ctx) return
  const stableLevel = metrics.level * 0.6
  const stableLow   = metrics.low   * 0.65
  const stableHigh  = metrics.high  * 0.5
  // Less points for smaller canvas to save performance
  const points      = width > 100 ? 1200 : 300 

  const PI = Math.PI
  const layers = [
    { sx: radiusX * 1.04, sy: radiusY * 1.04, ps:  PI * 0.55, alpha: 0.07,  blur: 20, w: 4, hue: hueA,                pulse: 0.55 },
    { sx: radiusX,        sy: radiusY,         ps:  0,         alpha: 0.22,  blur: 8, w: 1.5, hue: hueB,               pulse: 1.2 },
  ]

  for (const l of layers) {
    const path = buildCurvePoints(points, (p) => makePt(p, fx, fy, phase, l.sx, l.sy, l.ps))
    traceSmoothClosedCurve(path)
    const widthPulse = 0.93 + 0.14 * (0.5 + 0.5 * Math.sin(t * (1.1 + l.pulse * 0.25) + l.ps * 1.7))
    ctx.lineWidth   = (l.w * widthPulse + stableLow * 1.4 + stableLevel * 2.2) * params.lineWeight
    ctx.shadowBlur  = l.blur + stableLevel * 10
    ctx.shadowColor = `hsla(${l.hue}, 100%, 75%, ${(0.3 + stableHigh * 0.2) * alphaScale})`
    ctx.strokeStyle = `hsla(${l.hue}, 90%, 78%, ${l.alpha * alphaScale})`
    ctx.stroke()
  }

  const mainPath = buildCurvePoints(points, (p) => makePt(p, fx, fy, phase, radiusX, radiusY, 0))
  traceSmoothClosedCurve(mainPath)

  const grad = ctx.createLinearGradient(-radiusX, -radiusY, radiusX, radiusY)
  grad.addColorStop(0,    `hsla(${hueA},       100%, 80%, ${0.28 * alphaScale})`)
  grad.addColorStop(1,    `hsla(${hueB + 15},  100%, 76%, ${0.28 * alphaScale})`)

  ctx.shadowBlur  = 10 + stableLevel * 15
  ctx.shadowColor = `hsla(${hueB}, 100%, 70%, ${(0.45 + stableLevel * 0.2) * alphaScale})`
  const mainWidthPulse = 0.95 + 0.12 * (0.5 + 0.5 * Math.sin(t * 1.45 + phase))
  ctx.lineWidth   = (1.25 * mainWidthPulse + stableLow * 1.7 + stableLevel * 2.6) * params.lineWeight
  ctx.strokeStyle = grad
  ctx.stroke()

  ctx.globalCompositeOperation = "lighter"
  ctx.lineWidth   = (0.62 + 0.18 * mainWidthPulse + stableHigh * 1.1) * params.lineWeight
  ctx.shadowBlur  = 4 + stableHigh * 8
  ctx.strokeStyle = `hsla(${hueA}, 80%, 96%, ${(0.22 + stableLevel * 0.22) * alphaScale})`
  ctx.stroke()
  ctx.globalCompositeOperation = "source-over"
}

function drawRing(t: number, ringR: number, stableLevel: number, stableHigh: number, hueA: number, hueB: number) {
  if (!ctx) return
  const breathe = 1 + 0.018 * Math.sin(t * 3.2) + stableLevel * 0.04

  ctx.beginPath()
  ctx.arc(0, 0, ringR * breathe, 0, Math.PI * 2)
  ctx.lineWidth   = (1.2 + stableLevel * 1.5) * params.lineWeight
  ctx.shadowBlur  = 5 + stableHigh * 10 + stableLevel * 10
  ctx.shadowColor = `hsla(${hueB}, 100%, 78%, 0.55)`
  ctx.strokeStyle = `hsla(${hueA}, 100%, 80%, ${0.5 + stableLevel * 0.3})`
  ctx.stroke()
}

function drawCurve(t: number, metrics: AudioMetrics) {
  if (!ctx) return
  const stableLevel = metrics.level
  const stableMid   = metrics.mid
  const stableHigh  = metrics.high

  const minR    = Math.min(width, height) * params.minRadius
  const maxR    = Math.min(width, height) * params.maxRadius
  const expand  = clamp(stableLevel * 2.2, 0, 1)
  const radius  = minR + (maxR - minR) * Math.pow(expand, 1.8)

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

  const centerX = width  * 0.5
  const centerY = height * 0.5

  const baseSize = Math.min(width, height)
  const ringR    = radius + baseSize * params.ringGap
  const clipR    = ringR  * 0.96

  ctx.save()
  ctx.translate(centerX, centerY)
  ctx.lineJoin = "round"
  ctx.lineCap  = "round"

  drawRing(t, ringR, stableLevel, stableHigh, hueA, hueB)

  ctx.save()
  ctx.beginPath()
  ctx.arc(0, 0, clipR, 0, Math.PI * 2)
  ctx.clip()

  drawPair(t, fxA, fyA, phase, clipR, clipR, 1 - fade, metrics, hueA, hueB)
  if (fade > 0) {
    drawPair(t, fxB, fyB, phase, clipR, clipR, fade, metrics, hueA, hueB)
  }

  ctx.restore()
  ctx.restore()
}

function animate(now: number) {
  if (!ctx) return
  const t = now * 0.001
  const metrics = getAudioMetrics(t)

  const trailAlpha = (0.15 + (1 - clamp(metrics.level * 4, 0, 1)) * 0.18) / params.trail
  drawBackground(trailAlpha)
  drawCurve(t, metrics)

  animationFrameId = requestAnimationFrame(animate)
}

function handleResize() {
  if (!container.value || !canvasEl.value) return
  // Measure canvas size directly since it might be larger than container
  width = canvasEl.value.clientWidth
  height = canvasEl.value.clientHeight
  dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2))
  
  canvasEl.value.width = Math.floor(width * dpr)
  canvasEl.value.height = Math.floor(height * dpr)
  
  // Adjust line weight based on size
  params.lineWeight = clamp(width / 100, 0.5, 2.0)

  if (ctx) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    // Clear the canvas on resize
    ctx.clearRect(0, 0, width, height)
  }
}

onMounted(() => {
  if (canvasEl.value) {
    ctx = canvasEl.value.getContext('2d')
  }
  
  if (container.value) {
    resizeObserver = new ResizeObserver(() => {
      handleResize()
    })
    resizeObserver.observe(container.value)
    handleResize()
  }

  animationFrameId = requestAnimationFrame(animate)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(animationFrameId)
  if (resizeObserver && container.value) {
    resizeObserver.unobserve(container.value)
  }
})
</script>

<style scoped>
.lissajous-container {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  position: relative;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
}
canvas {
  display: block;
  width: 140%;
  height: 140%;
  position: absolute;
  pointer-events: none;
}
</style>
