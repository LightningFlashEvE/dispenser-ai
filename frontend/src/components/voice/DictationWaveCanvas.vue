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
  colorA: string,
  colorB: string,
  offset: number,
): void {
  if (!ctx) return

  const centerY = height / 2
  const gradient = ctx.createLinearGradient(0, centerY, width, centerY)
  gradient.addColorStop(0, colorA)
  gradient.addColorStop(0.5, `rgba(255,255,255,${alpha})`)
  gradient.addColorStop(1, colorB)

  ctx.beginPath()
  const steps = Math.max(48, Math.floor(width / 10))
  for (let i = 0; i <= steps; i += 1) {
    const x = (i / steps) * width
    const nx = x / width
    const envelope = Math.pow(Math.sin(nx * Math.PI), 1.35)
    const wobble =
      Math.sin(nx * 7.2 - phase * speed + offset) * 0.55 +
      Math.sin(nx * 14.4 + phase * speed * 1.3 + offset * 0.7) * 0.22
    const y = centerY + wobble * amplitude * envelope
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }

  ctx.strokeStyle = gradient
  ctx.lineWidth = lineWidth
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.shadowBlur = amplitude * 0.4
  ctx.shadowColor = `rgba(111, 190, 255, ${alpha * 0.55})`
  ctx.stroke()
}

function render(): void {
  if (!ctx) return

  displayedLevel += ((props.isActive ? props.level : 0) - displayedLevel) * (props.isActive ? 0.22 : 0.08)
  energy += ((props.isActive ? 0.55 + displayedLevel * 0.9 : 0.24) - energy) * 0.08
  phase += props.isActive ? 0.05 + displayedLevel * 0.14 : 0.025

  ctx.clearRect(0, 0, width, height)

  const speechLift = props.isActive ? 0.2 + displayedLevel * 1.55 : 0.16
  const baseAmplitude = height * speechLift * energy

  drawLine(
    baseAmplitude * (0.7 + displayedLevel * 0.1),
    0.9 + displayedLevel * 0.25,
    0.24 + displayedLevel * 0.18,
    1.25 + displayedLevel * 0.7,
    'rgba(122, 199, 255, 0.08)',
    'rgba(122, 199, 255, 0.18)',
    0.35,
  )
  drawLine(
    baseAmplitude * (0.92 + displayedLevel * 0.18),
    1.2 + displayedLevel * 0.5,
    0.58 + displayedLevel * 0.18,
    1.8 + displayedLevel * 1.2,
    'rgba(122, 199, 255, 0.22)',
    'rgba(255, 255, 255, 0.34)',
    1.1,
  )
  drawLine(
    baseAmplitude * (1.08 + displayedLevel * 0.42),
    1.55 + displayedLevel * 0.75,
    0.72 + displayedLevel * 0.22,
    2.2 + displayedLevel * 1.8,
    'rgba(180, 225, 255, 0.42)',
    'rgba(108, 179, 255, 0.56)',
    2.1,
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
