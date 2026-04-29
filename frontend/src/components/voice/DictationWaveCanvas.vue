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
let energy = 0.18
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

function drawLine(
  amplitude: number,
  speed: number,
  alpha: number,
  lineWidth: number,
  color: string,
  offset: number,
): void {
  if (!ctx) return

  const centerY = height / 2
  ctx.beginPath()
  const steps = Math.max(72, Math.floor(width / 8))
  for (let i = 0; i <= steps; i += 1) {
    const x = (i / steps) * width
    const nx = x / width
    const envelope = Math.pow(Math.sin(nx * Math.PI), 1.85)
    const wobble =
      Math.sin(nx * 6.2 - phase * speed + offset) * 0.72 +
      Math.sin(nx * 12.4 + phase * speed * 1.12 + offset * 0.6) * 0.18
    const y = centerY + wobble * amplitude * envelope
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }

  ctx.strokeStyle = color
  ctx.lineWidth = lineWidth
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.globalAlpha = alpha
  ctx.stroke()
  ctx.globalAlpha = 1
}

function drawBaseline(): void {
  if (!ctx) return
  const centerY = height / 2
  ctx.beginPath()
  ctx.moveTo(0, centerY)
  ctx.lineTo(width, centerY)
  ctx.strokeStyle = 'rgba(184, 198, 219, 0.18)'
  ctx.lineWidth = 1
  ctx.stroke()
}

function render(): void {
  if (!ctx) return

  displayedLevel += ((props.isActive ? props.level : 0) - displayedLevel) * (props.isActive ? 0.22 : 0.08)
  energy += ((props.isActive ? 0.55 + displayedLevel * 0.9 : 0.24) - energy) * 0.08
  phase += props.isActive ? 0.05 + displayedLevel * 0.14 : 0.025

  ctx.clearRect(0, 0, width, height)
  drawBaseline()

  const speechLift = props.isActive ? 0.08 + displayedLevel * 0.75 : 0.03
  const baseAmplitude = height * speechLift * energy

  drawLine(
    baseAmplitude * (0.65 + displayedLevel * 0.08),
    0.8 + displayedLevel * 0.22,
    0.26 + displayedLevel * 0.18,
    1,
    'rgba(163, 190, 224, 0.95)',
    0.3,
  )
  drawLine(
    baseAmplitude * (0.95 + displayedLevel * 0.28),
    1.1 + displayedLevel * 0.42,
    0.72 + displayedLevel * 0.2,
    1.8 + displayedLevel * 0.65,
    'rgba(230, 238, 249, 0.98)',
    1.15,
  )

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
