<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import Badge from '@/components/ui/badge/Badge.vue'
import Card from '@/components/ui/card/Card.vue'

const props = defineProps<{
  valueMg: number | null
  stable: boolean
  overLimit: boolean
}>()

const chartEl = ref<HTMLDivElement | null>(null)
const points = ref<Array<{ time: string; value: number }>>([])
let chart: echarts.ECharts | null = null

const status = computed(() => {
  if (props.overLimit) return { text: '异常', variant: 'danger' as const }
  if (props.valueMg === null) return { text: '无数据', variant: 'offline' as const }
  return props.stable ? { text: '稳定', variant: 'ok' as const } : { text: '波动', variant: 'warn' as const }
})

function formatWeightMg(value: number | null): string {
  if (value === null || value === undefined) return '--'
  return Math.abs(value) < 10 ? value.toFixed(3) : value.toFixed(0)
}

function formatPointTime(date: Date): string {
  const base = date.toLocaleTimeString('zh-CN', { hour12: false, minute: '2-digit', second: '2-digit' })
  return `${base}.${Math.floor(date.getMilliseconds() / 100)}`
}

function renderChart() {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  chart.setOption({
    grid: { left: 8, right: 8, top: 10, bottom: 18, containLabel: true },
    xAxis: { type: 'category', data: points.value.map((p) => p.time), axisLabel: { color: '#94a3b8', fontSize: 10 }, axisLine: { lineStyle: { color: '#243244' } } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8', fontSize: 10 }, splitLine: { lineStyle: { color: '#1f2a3a' } } },
    series: [{ type: 'line', data: points.value.map((p) => p.value), smooth: true, showSymbol: false, lineStyle: { color: '#06b6d4', width: 2 }, areaStyle: { color: 'rgba(6, 182, 212, 0.12)' } }],
    animation: false,
  })
}

watch(() => props.valueMg, (value) => {
  if (value === null || value === undefined) return
  points.value.push({ time: formatPointTime(new Date()), value })
  points.value = points.value.slice(-300)
  renderChart()
})

onMounted(() => {
  renderChart()
  window.addEventListener('resize', renderChart)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', renderChart)
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
