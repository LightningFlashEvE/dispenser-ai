<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import Badge from '@/components/ui/badge/Badge.vue'
import Card from '@/components/ui/card/Card.vue'

interface WeightPoint {
  ts: number
  value: number
}

const props = defineProps<{
  valueMg: number | null
  stable: boolean
  overLimit: boolean
  points?: WeightPoint[]
  pointsVersion?: number
}>()

const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let rafId: number | null = null

const status = computed(() => {
  if (props.overLimit) return { text: '异常', variant: 'danger' as const }
  if (props.valueMg === null) return { text: '无数据', variant: 'offline' as const }
  return props.stable ? { text: '稳定', variant: 'ok' as const } : { text: '波动', variant: 'warn' as const }
})

function formatWeightMg(value: number | null): string {
  if (value === null || value === undefined) return '--'
  return Math.abs(value) < 10 ? value.toFixed(3) : value.toFixed(0)
}

function renderChart() {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  const seriesPoints = props.points ?? []
  chart.setOption({
    grid: { left: 8, right: 8, top: 10, bottom: 18, containLabel: true },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value: unknown) => {
        const numericValue = Array.isArray(value) ? Number(value[1]) : Number(value)
        return Number.isFinite(numericValue) ? `${numericValue.toFixed(3)} mg` : '--'
      },
    },
    xAxis: {
      type: 'time',
      axisLabel: { color: '#94a3b8', fontSize: 10 },
      axisLine: { lineStyle: { color: '#243244' } },
    },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8', fontSize: 10 }, splitLine: { lineStyle: { color: '#1f2a3a' } } },
    series: [{
      type: 'line',
      data: seriesPoints.map((point) => [point.ts, point.value]),
      smooth: false,
      showSymbol: false,
      lineStyle: { color: '#06b6d4', width: 2 },
      areaStyle: { color: 'rgba(6, 182, 212, 0.12)' },
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
watch(() => props.points, scheduleRender)

onMounted(() => {
  renderChart()
  window.addEventListener('resize', scheduleRender)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', scheduleRender)
  if (rafId !== null) cancelAnimationFrame(rafId)
  chart?.dispose()
})
</script>

<template>
  <Card class="p-4">
    <div class="flex items-start justify-between">
      <div>
        <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">实时称重</div>
        <div class="mt-3 flex items-end gap-2">
          <span class="text-3xl font-semibold tabular-nums">{{ formatWeightMg(valueMg) }}</span>
          <span class="pb-1 text-sm text-muted-foreground">mg</span>
        </div>
      </div>
      <Badge :variant="status.variant">{{ status.text }}</Badge>
    </div>
    <div ref="chartEl" class="mt-4 h-36 w-full" />
  </Card>
</template>
