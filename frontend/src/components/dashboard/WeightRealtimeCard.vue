<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import Badge from '@/components/ui/badge/Badge.vue'
import Card from '@/components/ui/card/Card.vue'

interface WeightPoint {
  ts: number
  value: number
}

const DEFAULT_WINDOW_MS = 10_000
const AXIS_REFRESH_MS = 500
const AXIS_TICK_MS = 500
const MIN_Y_SPAN_MG = 5

const props = defineProps<{
  valueMg: number | null
  stable: boolean
  overLimit: boolean
  points?: WeightPoint[]
  pointsVersion?: number
  windowMs?: number
}>()

const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let rafId: number | null = null
let axisTimer: ReturnType<typeof setInterval> | null = null

const status = computed(() => {
  if (props.overLimit) return { text: '异常', variant: 'danger' as const }
  if (props.valueMg === null) return { text: '无数据', variant: 'offline' as const }
  return props.stable ? { text: '稳定', variant: 'ok' as const } : { text: '波动', variant: 'warn' as const }
})

function formatWeightMg(value: number | null): string {
  if (value === null || value === undefined) return '--'
  return Math.abs(value) < 10 ? value.toFixed(3) : value.toFixed(0)
}

function visiblePoints(now = Date.now()): WeightPoint[] {
  const chartWindowMs = props.windowMs ?? DEFAULT_WINDOW_MS
  const minTs = now - chartWindowMs
  const maxTs = now
  return (props.points ?? []).filter((point) => point.ts >= minTs && point.ts <= maxTs)
}

const stats = computed(() => {
  void props.pointsVersion
  const points = visiblePoints()
  if (!points.length) {
    return { min: null, avg: null, max: null, count: 0 }
  }
  const values = points.map((point) => point.value)
  const sum = values.reduce((total, value) => total + value, 0)
  return {
    min: Math.min(...values),
    avg: sum / values.length,
    max: Math.max(...values),
    count: values.length,
  }
})

function roundedAxisValue(value: number, direction: 'down' | 'up'): number {
  const absValue = Math.abs(value)
  const step = absValue >= 10000 ? 100 : absValue >= 1000 ? 10 : absValue >= 100 ? 1 : 0.1
  const scaled = value / step
  return (direction === 'down' ? Math.floor(scaled) : Math.ceil(scaled)) * step
}

function yAxisRange(points: WeightPoint[]): { min: number; max: number } {
  const values = points.map((point) => point.value)
  if (props.valueMg !== null) values.push(props.valueMg)
  if (!values.length) return { min: 0, max: MIN_Y_SPAN_MG }

  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const latest = props.valueMg ?? values[values.length - 1]
  const minSpan = Math.max(MIN_Y_SPAN_MG, Math.abs(latest) * 0.005)
  const rawSpan = rawMax - rawMin
  const span = Math.max(rawSpan, minSpan)
  const center = rawSpan < minSpan ? latest : (rawMin + rawMax) / 2
  const padding = Math.max(span * 0.18, minSpan * 0.12)
  const min = Math.max(0, center - span / 2 - padding)
  const max = center + span / 2 + padding
  return {
    min: roundedAxisValue(min, 'down'),
    max: roundedAxisValue(max, 'up'),
  }
}

function renderChart() {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  const chartWindowMs = props.windowMs ?? DEFAULT_WINDOW_MS
  const now = Date.now()
  const minTs = now - chartWindowMs
  const maxTs = now
  const seriesPoints = visiblePoints(now)
  const yRange = yAxisRange(seriesPoints)
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 4, right: 6, top: 8, bottom: 18, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15, 23, 42, 0.96)',
      borderColor: 'rgba(148, 163, 184, 0.24)',
      textStyle: { color: '#e2e8f0' },
      valueFormatter: (value: unknown) => {
        const numericValue = Array.isArray(value) ? Number(value[1]) : Number(value)
        return Number.isFinite(numericValue) ? `${numericValue.toFixed(3)} mg` : '--'
      },
    },
    xAxis: {
      type: 'time',
      min: minTs,
      max: maxTs,
      interval: AXIS_TICK_MS,
      axisTick: { show: false },
      axisLabel: {
        color: '#64748b',
        fontSize: 10,
        formatter: (value: number) => {
          const date = new Date(value)
          return date.getMilliseconds() === 0 ? date.toLocaleTimeString('zh-CN', { minute: '2-digit', second: '2-digit', hour12: false }) : ''
        },
      },
      axisLine: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      min: yRange.min,
      max: yRange.max,
      scale: false,
      axisTick: { show: false },
      axisLabel: { color: '#64748b', fontSize: 10, formatter: (value: number) => Number(value).toFixed(Math.abs(value) < 10 ? 1 : 0) },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.12)' } },
    },
    series: [{
      name: '重量',
      type: 'line',
      data: seriesPoints.map((point) => [point.ts, point.value]),
      smooth: 0.2,
      showSymbol: false,
      sampling: 'lttb',
      lineStyle: { color: props.stable ? '#22c55e' : '#06b6d4', width: 2.2, cap: 'round', join: 'round' },
      areaStyle: {
        opacity: 0.16,
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: props.stable ? 'rgba(34, 197, 94, 0.30)' : 'rgba(6, 182, 212, 0.30)' },
          { offset: 1, color: 'rgba(6, 182, 212, 0.02)' },
        ]),
      },
      emphasis: { disabled: true },
    }],
    animation: false,
  })
}

function scheduleRender() {
  if (rafId !== null) return
  rafId = requestAnimationFrame(() => {
    rafId = null
    renderChart()
  })
}

watch(() => props.pointsVersion, scheduleRender)

onMounted(() => {
  renderChart()
  axisTimer = setInterval(scheduleRender, AXIS_REFRESH_MS)
  window.addEventListener('resize', scheduleRender)
})
onBeforeUnmount(() => {
  if (axisTimer) clearInterval(axisTimer)
  window.removeEventListener('resize', scheduleRender)
  if (rafId !== null) cancelAnimationFrame(rafId)
  chart?.dispose()
})
</script>

<template>
  <Card class="p-4">
    <div class="flex items-start justify-between gap-3">
      <div>
        <div class="text-xs font-semibold uppercase tracking-wide text-cyan-300">实时称重</div>
        <div class="mt-3 flex items-end gap-2 leading-none">
          <span class="text-3xl font-semibold tabular-nums">{{ formatWeightMg(valueMg) }}</span>
          <span class="pb-0.5 text-sm text-muted-foreground">mg</span>
        </div>
        <div class="mt-2 text-xs text-muted-foreground">10 秒窗口 · 500ms 显示采样</div>
      </div>
      <Badge :variant="status.variant">{{ status.text }}</Badge>
    </div>
    <div class="mt-4 grid grid-cols-3 gap-2 text-xs">
      <div class="rounded-md border border-border/70 bg-muted/20 px-2 py-1.5">
        <div class="text-muted-foreground">Min</div>
        <div class="mt-0.5 font-mono text-foreground">{{ formatWeightMg(stats.min) }}</div>
      </div>
      <div class="rounded-md border border-border/70 bg-muted/20 px-2 py-1.5">
        <div class="text-muted-foreground">Avg</div>
        <div class="mt-0.5 font-mono text-foreground">{{ formatWeightMg(stats.avg) }}</div>
      </div>
      <div class="rounded-md border border-border/70 bg-muted/20 px-2 py-1.5">
        <div class="text-muted-foreground">Max</div>
        <div class="mt-0.5 font-mono text-foreground">{{ formatWeightMg(stats.max) }}</div>
      </div>
    </div>
    <div ref="chartEl" class="mt-3 h-36 w-full" />
  </Card>
</template>
