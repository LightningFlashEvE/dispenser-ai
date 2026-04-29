<template>
  <div ref="containerEl" class="dictation-wave-canvas">
    <canvas ref="canvasEl" class="dictation-wave-canvas__surface"></canvas>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  isActive: boolean
  level: number
}>()

const containerEl = ref<HTMLElement | null>(null)
const canvasEl = ref<HTMLCanvasElement | null>(null)

let ctx: CanvasRenderingContext2D | null = null
let resizeObserver: ResizeObserver | null = null
let frameId = 0
let width = 0
let height = 0
let dpr = 1
let phase = 0
let displayedLevel = 0

function resizeCanvas(): void {
  if (!containerEl.value || !canvasEl.value || !ctx) return

  width = Math.max(1, Math.floor(containerEl.value.clientWidth))
  height = Math.max(1, Math.floor(containerEl.value.clientHeight))
  dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2))

  canvasEl.value.width = Math.floor(width * dpr)
  canvasEl.value.height = Math.floor(height * dpr)
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

function drawBars(level: number): void {
  if (!ctx) return

  const centerY = height / 2
  const barStep = 6
  const barCount = Math.max(24, Math.floor(width / barStep))
  const activeLevel = props.isActive ? level : 0
  const baseHeight = props.isActive ? height * 0.08 : height * 0.035
  const peakHeight = props.isActive ? height * (0.22 + activeLevel * 0.58) : height * 0.08

  ctx.lineCap = 'round'

  for (let i = 0; i < barCount; i += 1) {
    const x = ((i + 0.5) / barCount) * width
    const normalized = i / Math.max(1, barCount - 1)
    const envelope = Math.pow(Math.sin(normalized * Math.PI), 1.35)
    const pulseA = Math.sin(normalized * 10.8 - phase * 1.9)
    const pulseB = Math.sin(normalized * 24.0 + phase * 2.8)
    const shimmer = Math.sin(normalized * 4.8 + phase * 0.65)
    const turbulence = 0.58 + pulseA * 0.3 + pulseB * 0.12
    const amplitude = baseHeight + peakHeight * envelope * clamp(turbulence, 0.18, 1)
    const barHeight = clamp(amplitude, 2, height * 0.92)
    const halfHeight = barHeight / 2

    const alpha = props.isActive
      ? clamp(0.22 + envelope * 0.34 + activeLevel * 0.28 + shimmer * 0.04, 0.18, 0.88)
      : 0.16
    const lineWidth = props.isActive && envelope > 0.55 ? 1.6 : 1.2

    ctx.beginPath()
    ctx.moveTo(x, centerY - halfHeight)
    ctx.lineTo(x, centerY + halfHeight)
    ctx.strokeStyle = `rgba(226, 234, 245, ${alpha.toFixed(3)})`
    ctx.lineWidth = lineWidth
    ctx.stroke()
  }
}

function render(): void {
  if (!ctx) return

  displayedLevel += ((props.isActive ? props.level : 0) - displayedLevel) * (props.isActive ? 0.26 : 0.1)
  phase += props.isActive ? 0.08 + displayedLevel * 0.18 : 0.03

  ctx.clearRect(0, 0, width, height)
  drawBars(displayedLevel)

  frameId = requestAnimationFrame(render)
}

onMounted(() => {
  ctx = canvasEl.value?.getContext('2d') ?? null
  if (!ctx) return

  resizeObserver = new ResizeObserver(() => resizeCanvas())
  if (containerEl.value) resizeObserver.observe(containerEl.value)
  resizeCanvas()
  frameId = requestAnimationFrame(render)
})

watch(() => props.isActive, () => {
  if (!frameId && ctx) frameId = requestAnimationFrame(render)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(frameId)
  resizeObserver?.disconnect()
})
</script>

<style scoped>
.dictation-wave-canvas {
  width: 100%;
  height: 100%;
  position: relative;
}

.dictation-wave-canvas__surface {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
