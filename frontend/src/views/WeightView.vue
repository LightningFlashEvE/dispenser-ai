<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle, Scale } from 'lucide-vue-next'
import WeightRealtimeCard from '@/components/dashboard/WeightRealtimeCard.vue'
import Badge from '@/components/ui/badge/Badge.vue'
import Card from '@/components/ui/card/Card.vue'
import { useVoiceStore } from '@/stores/voice'

const voiceStore = useVoiceStore()
const status = computed(() => {
  if (voiceStore.balanceOverLimit) return { text: '异常 / 超限', variant: 'danger' as const }
  if (voiceStore.balanceMg === null) return { text: '等待数据', variant: 'offline' as const }
  return voiceStore.balanceStable ? { text: '稳定', variant: 'ok' as const } : { text: '波动', variant: 'warn' as const }
})
</script>

<template>
  <div class="h-full overflow-y-auto bg-background p-5">
    <header class="mb-5 flex flex-wrap items-center justify-between gap-4">
      <div>
        <div class="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">Balance Monitor</div>
        <h1 class="mt-1 text-2xl font-semibold">实时称重</h1>
        <p class="mt-1 text-sm text-muted-foreground">复用现有 WebSocket 称重事件，不新增称重接口或设备控制逻辑。</p>
      </div>
      <Badge :variant="status.variant">{{ status.text }}</Badge>
    </header>

    <div class="grid grid-cols-1 gap-5 xl:grid-cols-[520px_1fr]">
      <WeightRealtimeCard
        :value-mg="voiceStore.balanceMg"
        :stable="voiceStore.balanceStable"
        :over-limit="voiceStore.balanceOverLimit"
      />
      <Card class="p-4">
        <div class="mb-4 flex items-center gap-2">
          <Scale class="h-4 w-4 text-cyan-300" />
          <h2 class="text-sm font-semibold">称重状态说明</h2>
        </div>
        <div class="space-y-3 text-sm text-muted-foreground">
          <div class="rounded-md border border-border bg-muted/30 p-3">
            当前重量：<span class="font-mono text-foreground">{{ voiceStore.balanceMg !== null ? `${voiceStore.balanceMg.toFixed(0)} mg` : '暂无数据' }}</span>
          </div>
          <div class="rounded-md border border-border bg-muted/30 p-3">
            稳定状态：<span class="text-foreground">{{ voiceStore.balanceStable ? '稳定' : '未稳定 / 波动' }}</span>
          </div>
          <div class="rounded-md border border-border bg-muted/30 p-3">
            数据来源：`/ws/voice` 的 `balance_reading` 和 `balance_over_limit` 事件。
          </div>
          <div v-if="voiceStore.balanceOverLimit" class="flex gap-2 rounded-md border border-red-400/30 bg-red-500/10 p-3 text-red-200">
            <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0" />
            检测到超限事件，请按设备现场流程处理，前端不会自动复位或绕过后端安全状态机。
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>
