<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { AlertTriangle, Bot, CheckCircle2, Cpu, Gauge, RadioTower, Scale, Server, Thermometer, Timer } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import AlarmList from '@/components/dashboard/AlarmList.vue'
import ConnectionBadge from '@/components/common/ConnectionBadge.vue'
import DeviceStatusCard from '@/components/dashboard/DeviceStatusCard.vue'
import LogStream from '@/components/dashboard/LogStream.vue'
import ServiceHealthGrid from '@/components/dashboard/ServiceHealthGrid.vue'
import StatusCard from '@/components/dashboard/StatusCard.vue'
import TaskProgressCard from '@/components/dashboard/TaskProgressCard.vue'
import WeightRealtimeCard from '@/components/dashboard/WeightRealtimeCard.vue'
import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import Card from '@/components/ui/card/Card.vue'
import Progress from '@/components/ui/progress/Progress.vue'
import Separator from '@/components/ui/separator/Separator.vue'
import Tabs from '@/components/ui/tabs/Tabs.vue'
import { deviceApi, systemApi, taskApi, type DeviceStatus, type SystemResources, type Task } from '@/services/api'
import { useVoiceStore } from '@/stores/voice'
import { resourceBarClass } from '@/lib/status'

const voiceStore = useVoiceStore()
const now = ref(new Date())
const resources = ref<SystemResources | null>(null)
const deviceStatus = ref<DeviceStatus | null>(null)
const tasks = ref<Task[]>([])
const resourcesError = ref<string | null>(null)
const deviceError = ref<string | null>(null)
const tasksError = ref<string | null>(null)
const loading = ref(true)
const activeLogTab = ref('logs')
let clockTimer: ReturnType<typeof setInterval> | null = null
let refreshTimer: ReturnType<typeof setInterval> | null = null

const currentTask = computed(() =>
  tasks.value.find((task) => ['EXECUTING', 'PROCESSING', 'PENDING', 'RUNNING'].includes(task.status?.toUpperCase())) ??
  tasks.value[0] ??
  null,
)
const alarms = computed(() =>
  tasks.value.filter((task) => {
    const status = task.status?.toUpperCase() ?? ''
    return status.includes('FAILED') || status.includes('ERROR') || Boolean(task.error_message)
  }),
)
const todayTasks = computed(() => {
  const today = new Date().toDateString()
  return tasks.value.filter((task) => new Date(task.created_at).toDateString() === today).length
})
const onlineDeviceCount = computed(() => {
  let count = 0
  if (deviceStatus.value?.device_status && deviceStatus.value.device_status.toLowerCase() !== 'offline') count += 1
  if (deviceStatus.value?.balance_ready) count += 1
  if (voiceStore.isConnected) count += 3
  return count
})
const backendOnline = computed(() => Boolean(deviceStatus.value) && !deviceError.value)
const currentTime = computed(() => now.value.toLocaleString('zh-CN', { hour12: false }))
const taskStatus = computed(() => currentTask.value?.status ?? voiceStore.stateLabel)
const aiHealth = computed(() => voiceStore.isConnected ? 'ASR / LLM / TTS 通道在线' : '语音 AI 通道离线')
const resourceItems = computed(() => {
  if (!resources.value) return []
  return [
    { label: 'CPU', value: resources.value.cpu.percent, detail: `${resources.value.cpu.cores} 核` },
    { label: '内存', value: resources.value.memory.percent, detail: `${resources.value.memory.used_mb.toFixed(0)} / ${resources.value.memory.total_mb.toFixed(0)} MB` },
    { label: 'GPU', value: resources.value.gpu.percent, detail: `${resources.value.gpu.used_mb.toFixed(0)} / ${resources.value.gpu.total_mb.toFixed(0)} MB` },
    { label: '磁盘', value: resources.value.disk.percent, detail: `${resources.value.disk.used_gb.toFixed(1)} / ${resources.value.disk.total_gb.toFixed(1)} GB` },
  ]
})
const deviceDetailRows = computed(() => [
  { label: '设备状态', value: deviceStatus.value?.device_status ?? '未知' },
  { label: '状态机', value: deviceStatus.value?.state_machine_state ?? '未知' },
  { label: '天平就绪', value: deviceStatus.value?.balance_ready ? '就绪' : '未就绪 / 未知' },
  { label: '当前任务', value: deviceStatus.value?.current_task_id ?? '无' },
  { label: '当前命令', value: deviceStatus.value?.current_command_id ?? '无' },
])

async function refreshDashboard() {
  loading.value = true
  await Promise.all([fetchDevice(), fetchResources(), fetchTasks()])
  loading.value = false
}

async function fetchDevice() {
  try {
    deviceStatus.value = await deviceApi.status()
    deviceError.value = null
  } catch (error) {
    deviceError.value = error instanceof Error ? error.message : '设备状态接口不可用'
  }
}

async function fetchResources() {
  try {
    resources.value = await systemApi.resources()
    resourcesError.value = null
  } catch (error) {
    resourcesError.value = error instanceof Error ? error.message : '系统资源接口不可用'
  }
}

async function fetchTasks() {
  try {
    tasks.value = await taskApi.list({ limit: 80 })
    tasksError.value = null
  } catch (error) {
    tasksError.value = error instanceof Error ? error.message : '任务接口不可用'
  }
}

function cancelCurrentTask() {
  voiceStore.cancelTask()
  toast.warning('已发送停止请求', { description: '请求通过现有 WebSocket cancel 事件发出，最终状态以后端返回为准。' })
}

onMounted(() => {
  refreshDashboard()
  clockTimer = setInterval(() => { now.value = new Date() }, 1000)
  refreshTimer = setInterval(() => { refreshDashboard() }, 15000)
})
onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer)
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
  <div class="h-full overflow-y-auto bg-[radial-gradient(circle_at_top_left,rgba(6,182,212,0.12),transparent_34%),#050b12]">
    <header class="sticky top-0 z-20 border-b border-border bg-background/90 px-5 py-4 backdrop-blur">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div class="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">AI High-throughput Solid Dispenser</div>
          <h1 class="mt-1 text-2xl font-semibold tracking-normal">智能配料工业控制台</h1>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <ConnectionBadge label="后端" :connected="backendOnline" :loading="loading && !deviceStatus" :error="Boolean(deviceError)" />
          <ConnectionBadge label="WebSocket" :connected="voiceStore.isConnected" />
          <Badge :variant="voiceStore.isConnected ? 'ok' : 'offline'">ASR</Badge>
          <Badge :variant="voiceStore.isConnected ? 'ok' : 'offline'">LLM</Badge>
          <Badge :variant="voiceStore.isConnected ? 'ok' : 'offline'">TTS</Badge>
          <Badge variant="info"><Timer class="mr-1 h-3 w-3" />{{ currentTime }}</Badge>
        </div>
      </div>
      <div v-if="deviceError || tasksError || voiceStore.errorMsg" class="mt-3 rounded-md border border-amber-400/25 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
        {{ deviceError || tasksError || voiceStore.errorMsg }}
      </div>
    </header>

    <main class="space-y-5 p-5">
      <section class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-6">
        <StatusCard title="设备在线数量" :value="`${onlineDeviceCount}/6`" :detail="deviceStatus?.device_status || '等待设备状态'" :status="backendOnline ? 'ok' : 'offline'" :icon="Server" />
        <StatusCard title="当前任务状态" :value="taskStatus" :detail="currentTask?.task_id || '暂无任务 ID'" :status="currentTask ? 'info' : 'offline'" :icon="Gauge" />
        <StatusCard title="当前称重" :value="voiceStore.balanceMg !== null ? voiceStore.balanceMg.toFixed(0) : '--'" detail="mg" :status="voiceStore.balanceOverLimit ? 'danger' : voiceStore.balanceStable ? 'ok' : 'warn'" :icon="Scale" />
        <StatusCard title="今日任务" :value="todayTasks" :detail="`${tasks.length} 条近期记录`" status="info" :icon="CheckCircle2" />
        <StatusCard title="报警数量" :value="alarms.length" :detail="alarms.length ? '需要人工确认' : '暂无报警'" :status="alarms.length ? 'danger' : 'ok'" :icon="AlertTriangle" />
        <StatusCard title="AI 服务" :value="voiceStore.isConnected ? '健康' : '离线'" :detail="aiHealth" :status="voiceStore.isConnected ? 'ok' : 'offline'" :icon="Bot" />
      </section>

      <section class="grid grid-cols-1 gap-5 xl:grid-cols-[1.1fr_0.9fr]">
        <TaskProgressCard :task="currentTask" :state-label="voiceStore.stateLabel" :can-cancel="voiceStore.isConnected && Boolean(currentTask)" @cancel="cancelCurrentTask" />
        <WeightRealtimeCard :value-mg="voiceStore.balanceMg" :stable="voiceStore.balanceStable" :over-limit="voiceStore.balanceOverLimit" />
      </section>

      <section class="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_420px]">
        <Card class="p-4">
          <div class="mb-4 flex items-center justify-between">
            <div>
              <h2 class="text-sm font-semibold">设备状态</h2>
              <p class="mt-1 text-xs text-muted-foreground">已合并原“系统状态”页的设备状态接口字段。</p>
            </div>
            <Button variant="outline" size="sm" @click="refreshDashboard">刷新</Button>
          </div>
          <div class="mb-4 grid grid-cols-1 gap-2 rounded-md border border-border bg-muted/20 p-3 md:grid-cols-5">
            <div v-for="row in deviceDetailRows" :key="row.label" class="min-w-0">
              <div class="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{{ row.label }}</div>
              <div class="mt-1 truncate text-sm font-medium text-foreground" :title="row.value">{{ row.value }}</div>
            </div>
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            <DeviceStatusCard name="机械臂" :status="backendOnline ? 'online' : 'unknown'" :detail="deviceStatus?.state_machine_state || '状态机未知'" :icon="RadioTower" />
            <DeviceStatusCard name="天平" :status="deviceStatus?.balance_ready ? 'online' : 'warning'" :detail="deviceStatus?.balance_ready ? '已就绪' : '未就绪或未知'" :icon="Scale" />
            <DeviceStatusCard name="摄像头" status="unknown" detail="当前前端未发现摄像头状态接口" />
            <DeviceStatusCard name="语音模块" :status="voiceStore.isConnected ? 'online' : 'offline'" :detail="voiceStore.stateLabel" />
            <DeviceStatusCard name="LLM 服务" :status="voiceStore.isConnected ? 'running' : 'unknown'" :detail="aiHealth" :icon="Bot" />
            <DeviceStatusCard name="TTS 服务" :status="voiceStore.isConnected ? 'online' : 'unknown'" detail="通过 /ws/voice 返回音频事件" />
          </div>
          <Separator class="my-4" />
          <ServiceHealthGrid :websocket-online="voiceStore.isConnected" :backend-online="backendOnline" :ai-state="voiceStore.stateLabel" />
        </Card>

        <Card class="p-4">
          <div class="mb-4 flex items-center gap-2">
            <Cpu class="h-4 w-4 text-cyan-300" />
            <h2 class="text-sm font-semibold">系统资源</h2>
          </div>
          <div v-if="resourcesError" class="rounded-md border border-slate-500/30 bg-slate-500/10 p-3 text-sm text-muted-foreground">
            {{ resourcesError }}
          </div>
          <div v-else-if="!resourceItems.length" class="space-y-3">
            <div v-for="i in 4" :key="i" class="h-9 animate-pulse rounded-md bg-muted" />
          </div>
          <div v-else class="space-y-4">
            <div v-for="item in resourceItems" :key="item.label">
              <div class="mb-2 flex items-center justify-between text-xs">
                <span class="font-semibold text-muted-foreground">{{ item.label }}</span>
                <span class="font-mono">{{ item.value.toFixed(1) }}% · {{ item.detail }}</span>
              </div>
              <Progress :model-value="item.value" :indicator-class="resourceBarClass(item.value)" />
            </div>
            <div class="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              <Thermometer class="h-4 w-4" />
              温度字段当前接口未提供，已保留资源区域但不展示假数据。
            </div>
          </div>
        </Card>
      </section>

      <section class="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_420px]">
        <Tabs v-model="activeLogTab" :tabs="[{ label: '任务日志', value: 'logs' }, { label: '接口状态', value: 'errors' }]">
          <template #logs>
            <LogStream :logs="tasks" :loading="loading" />
          </template>
          <template #errors>
            <Card class="p-4 text-sm text-muted-foreground">
              <div>后端：{{ deviceError || '正常' }}</div>
              <div class="mt-2">任务接口：{{ tasksError || '正常' }}</div>
              <div class="mt-2">资源接口：{{ resourcesError || '正常' }}</div>
              <div class="mt-2">WebSocket：{{ voiceStore.isConnected ? '正常' : '断开' }}</div>
            </Card>
          </template>
        </Tabs>
        <AlarmList :alarms="alarms" :loading="loading" />
      </section>
    </main>
  </div>
</template>
