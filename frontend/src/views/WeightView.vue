<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { AlertTriangle, Scale } from 'lucide-vue-next'
import WeightRealtimeCard from '@/components/dashboard/WeightRealtimeCard.vue'
import Badge from '@/components/ui/badge/Badge.vue'
import Card from '@/components/ui/card/Card.vue'
import { deviceApi, type DeviceStatus } from '@/services/api'
import { useVoiceStore } from '@/stores/voice'
import { balanceStatusDescriptor } from '@/lib/status'

const voiceStore = useVoiceStore()
const deviceStatus = ref<DeviceStatus | null>(null)
let refreshTimer: ReturnType<typeof setInterval> | null = null

const displayWeightMg = computed(() => voiceStore.balanceMg ?? deviceStatus.value?.current_weight_mg ?? null)
const displayWeightStable = computed(() => {
  if (voiceStore.balanceMg !== null) return voiceStore.balanceStable
  return displayWeightMg.value !== null
})
const displayWeightOverLimit = computed(() => {
  if (voiceStore.balanceMg !== null) return voiceStore.balanceOverLimit
  return false
})
const status = computed(() => balanceStatusDescriptor(displayWeightMg.value, displayWeightStable.value, displayWeightOverLimit.value))

async function fetchDevice() {
  try {
    deviceStatus.value = await deviceApi.status()
  } catch {
    // WeightView keeps its last known display and avoids replacing it with an error blank state.
  }
}

onMounted(() => {
  fetchDevice()
  refreshTimer = setInterval(fetchDevice, 5000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
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
      <Badge :variant="status.tone">{{ status.label }}</Badge>
    </header>

    <div class="grid grid-cols-1 gap-5 xl:grid-cols-[520px_1fr]">
      <WeightRealtimeCard
        :value-mg="displayWeightMg"
        :stable="displayWeightStable"
        :over-limit="displayWeightOverLimit"
      />
      <Card class="p-4">
        <div class="mb-4 flex items-center gap-2">
          <Scale class="h-4 w-4 text-cyan-300" />
          <h2 class="text-sm font-semibold">称重状态说明</h2>
        </div>
        <div class="space-y-3 text-sm text-muted-foreground">
          <div class="rounded-md border border-border bg-muted/30 p-3">
            当前重量：<span class="font-mono text-foreground">{{ displayWeightMg !== null ? `${displayWeightMg.toFixed(0)} mg` : '暂无数据' }}</span>
          </div>
          <div class="rounded-md border border-border bg-muted/30 p-3">
            稳定状态：<span class="text-foreground">{{ displayWeightStable ? '稳定' : '未稳定 / 波动' }}</span>
          </div>
          <div class="rounded-md border border-border bg-muted/30 p-3">
            数据来源：优先使用 `/ws/voice` 的 `balance_reading` / `balance_over_limit`，缺失时回退到 `/api/device/status.current_weight_mg`。
          </div>
          <div v-if="displayWeightOverLimit" class="flex gap-2 rounded-md border border-red-400/30 bg-red-500/10 p-3 text-red-200">
            <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0" />
            检测到超限事件，请按设备现场流程处理，前端不会自动复位或绕过后端安全状态机。
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>
