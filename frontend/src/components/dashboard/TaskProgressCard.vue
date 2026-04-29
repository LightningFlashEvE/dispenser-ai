<script setup lang="ts">
import { computed } from 'vue'
import { Pause, Play, Square } from 'lucide-vue-next'
import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import Card from '@/components/ui/card/Card.vue'
import Progress from '@/components/ui/progress/Progress.vue'
import ConfirmActionDialog from '@/components/common/ConfirmActionDialog.vue'
import type { Task } from '@/services/api'
import { taskStatusDescriptor } from '@/lib/status'

const props = defineProps<{
  task: Task | null
  stateLabel: string
  canCancel: boolean
}>()
const emit = defineEmits<{ cancel: [] }>()

const taskName = computed(() => props.task?.command_type || props.task?.task_id || '暂无执行任务')
const status = computed(() => props.task?.status || props.stateLabel || 'IDLE')
const progress = computed(() => {
  const value = status.value.toUpperCase()
  if (value.includes('COMPLETED')) return 100
  if (value.includes('FAILED') || value.includes('CANCEL')) return 100
  if (value.includes('EXECUT') || value.includes('PROCESS') || value.includes('THINK')) return 58
  if (value.includes('ASK') || value.includes('CONFIRM')) return 35
  return props.task ? 12 : 0
})
const statusDescriptor = computed(() => taskStatusDescriptor(status.value))
</script>

<template>
  <Card class="p-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">当前任务</div>
        <h2 class="mt-2 text-lg font-semibold">{{ taskName }}</h2>
        <div class="mt-1 text-xs text-muted-foreground">
          当前步骤：{{ task?.command_type || stateLabel || '待机' }}
        </div>
      </div>
      <Badge :variant="statusDescriptor.tone">{{ status }}</Badge>
    </div>
    <Progress class="mt-5" :model-value="progress" />
    <div class="mt-4 grid grid-cols-3 gap-2">
      <ConfirmActionDialog action-name="启动任务" risk="启动任务会进入后端确认和状态机流程；Dashboard 不直接构造新任务。" :current-state="status" :disabled="true">
        <Button variant="secondary" class="w-full" disabled><Play class="h-4 w-4" />启动</Button>
      </ConfirmActionDialog>
      <ConfirmActionDialog action-name="暂停 / 恢复任务" risk="当前后端未暴露暂停接口，界面仅保留入口，不绕过设备状态机。" :current-state="status" :disabled="true">
        <Button variant="secondary" class="w-full" disabled><Pause class="h-4 w-4" />暂停</Button>
      </ConfirmActionDialog>
      <ConfirmActionDialog action-name="停止任务" risk="停止会向现有 WebSocket 发送 cancel 指令，由后端处理规则、白名单和状态机。" :current-state="status" destructive confirm-text="确认停止" :disabled="!canCancel" @confirm="emit('cancel')">
        <Button variant="destructive" class="w-full" :disabled="!canCancel"><Square class="h-4 w-4" />停止</Button>
      </ConfirmActionDialog>
    </div>
  </Card>
</template>
