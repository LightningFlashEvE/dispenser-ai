<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { AlertTriangle, CheckCircle2, RefreshCw, Search, XCircle } from 'lucide-vue-next'
import { Badge, Button, Card, Input, Select, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui'
import { EmptyState, ErrorState, LoadingState, MetricGrid, PageHeader } from '@/components/common'
import { taskApi, type Task } from '@/services/api'
import { taskStatusDescriptor, type StatusTone } from '@/lib/status'

const logs = ref<Task[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const filterStatus = ref('ALL')
const query = ref('')
let refreshTimer: ReturnType<typeof setInterval> | null = null
let refreshInFlight = false
let logsSnapshot = ''

const statusOptions = [
  { label: '全部状态', value: 'ALL' },
  { label: '执行中', value: 'EXECUTING' },
  { label: '完成', value: 'COMPLETED' },
  { label: '失败', value: 'FAILED' },
  { label: '已取消', value: 'CANCELLED' },
]

const filteredLogs = computed(() => {
  const text = query.value.trim().toLowerCase()
  if (!text) return logs.value
  return logs.value.filter((item) =>
    [
      item.task_id,
      item.command_id,
      item.command_type,
      item.operator_id,
      item.status,
      item.error_message,
    ].some((value) => value?.toLowerCase().includes(text)),
  )
})

const failedCount = computed(() => logs.value.filter((item) => taskStatusDescriptor(item.status).tone === 'danger').length)
const completedCount = computed(() => logs.value.filter((item) => taskStatusDescriptor(item.status).tone === 'ok').length)
const activeCount = computed(() => logs.value.filter((item) => taskStatusDescriptor(item.status).tone === 'info').length)

onMounted(() => {
  fetchLogs()
  refreshTimer = setInterval(() => { fetchLogs(true) }, 1000)
})
onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

async function fetchLogs(silent = false) {
  if (refreshInFlight) return
  refreshInFlight = true
  if (!silent) loading.value = true
  if (!silent) error.value = null
  try {
    const nextLogs = await taskApi.list({
      status: filterStatus.value === 'ALL' ? undefined : filterStatus.value,
      limit: 200,
    })
    const nextSnapshot = JSON.stringify(nextLogs)
    if (nextSnapshot !== logsSnapshot) {
      logs.value = nextLogs
      logsSnapshot = nextSnapshot
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '日志加载失败'
  } finally {
    if (!silent) loading.value = false
    refreshInFlight = false
  }
}

function onStatusChange(value: string) {
  filterStatus.value = value
  fetchLogs()
}

function statusTone(status: string): StatusTone {
  return taskStatusDescriptor(status).tone
}

function fmtDate(iso: string | null) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '-'
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<template>
  <div class="h-full overflow-y-auto bg-background p-5">
    <PageHeader
      eyebrow="Audit & Alarm"
      title="日志报警"
      description="读取现有任务接口，不修改后端日志、任务状态或设备控制流程。"
    >
      <template #actions>
        <Button variant="outline" :disabled="loading" @click="fetchLogs">
          <RefreshCw class="h-4 w-4" :class="loading ? 'animate-spin' : ''" />
          刷新
        </Button>
      </template>
    </PageHeader>

    <MetricGrid columns="auto" class="mb-5">
      <Card class="p-4">
        <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">近期任务</div>
        <div class="mt-3 text-2xl font-semibold tabular-nums">{{ logs.length }}</div>
      </Card>
      <Card class="p-4">
        <div class="flex items-center justify-between gap-2">
          <div>
            <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">执行中</div>
            <div class="mt-3 text-2xl font-semibold tabular-nums">{{ activeCount }}</div>
          </div>
          <Badge variant="info">running</Badge>
        </div>
      </Card>
      <Card class="p-4">
        <div class="flex items-center justify-between gap-2">
          <div>
            <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">完成</div>
            <div class="mt-3 text-2xl font-semibold tabular-nums">{{ completedCount }}</div>
          </div>
          <CheckCircle2 class="h-5 w-5 text-emerald-300" />
        </div>
      </Card>
      <Card class="p-4">
        <div class="flex items-center justify-between gap-2">
          <div>
            <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">失败 / 报警</div>
            <div class="mt-3 text-2xl font-semibold tabular-nums">{{ failedCount }}</div>
          </div>
          <AlertTriangle class="h-5 w-5 text-red-300" />
        </div>
      </Card>
    </MetricGrid>

    <Card class="p-4">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div class="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <div class="relative w-full min-w-56 max-w-sm">
            <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input v-model="query" class="pl-9" placeholder="搜索任务 ID / 命令 / 操作员 / 错误信息" />
          </div>
          <Select :model-value="filterStatus" :options="statusOptions" class="w-36" @update:model-value="onStatusChange" />
        </div>
        <Badge variant="secondary">{{ filteredLogs.length }} 条显示</Badge>
      </div>

      <ErrorState v-if="error" :message="error" retry-label="重新加载" @retry="fetchLogs" />
      <LoadingState v-else-if="loading" :rows="8" />
      <EmptyState v-else-if="filteredLogs.length === 0" title="暂无日志" description="当前筛选条件下没有任务记录。" />
      <Table v-else>
        <TableHeader>
          <TableRow>
            <TableHead class="min-w-52">任务 ID</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>指令类型</TableHead>
            <TableHead>操作员</TableHead>
            <TableHead class="min-w-52">命令 ID</TableHead>
            <TableHead>开始时间</TableHead>
            <TableHead>完成时间</TableHead>
            <TableHead class="min-w-64">错误信息</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="row in filteredLogs" :key="row.task_id">
            <TableCell class="font-mono text-xs text-cyan-100">{{ row.task_id }}</TableCell>
            <TableCell>
              <Badge :variant="statusTone(row.status)">{{ row.status }}</Badge>
            </TableCell>
            <TableCell>{{ row.command_type || '-' }}</TableCell>
            <TableCell>{{ row.operator_id || '-' }}</TableCell>
            <TableCell class="font-mono text-xs text-muted-foreground">{{ row.command_id || '-' }}</TableCell>
            <TableCell class="whitespace-nowrap text-muted-foreground">{{ fmtDate(row.started_at) }}</TableCell>
            <TableCell class="whitespace-nowrap text-muted-foreground">{{ fmtDate(row.completed_at) }}</TableCell>
            <TableCell>
              <span v-if="row.error_message" class="inline-flex items-center gap-1 text-red-300">
                <XCircle class="h-3.5 w-3.5" />
                {{ row.error_message }}
              </span>
              <span v-else class="text-muted-foreground">-</span>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </Card>
  </div>
</template>
