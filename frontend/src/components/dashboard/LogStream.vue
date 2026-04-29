<script setup lang="ts">
import Badge from '@/components/ui/badge/Badge.vue'
import Card from '@/components/ui/card/Card.vue'
import ScrollArea from '@/components/ui/scroll-area/ScrollArea.vue'
import type { Task } from '@/services/api'

defineProps<{ logs: Task[]; loading?: boolean }>()

function fmt(iso: string | null) {
  if (!iso) return '--:--'
  return new Date(iso).toLocaleTimeString('zh-CN', { hour12: false })
}
function variant(status: string) {
  const value = status.toUpperCase()
  if (value.includes('FAILED') || value.includes('ERROR')) return 'danger'
  if (value.includes('COMPLETED')) return 'ok'
  if (value.includes('CANCEL')) return 'offline'
  return 'info'
}
</script>

<template>
  <Card class="p-4">
    <div class="mb-3 flex items-center justify-between">
      <div class="text-sm font-semibold">最近日志</div>
      <Badge variant="secondary">{{ logs.length }} 条</Badge>
    </div>
    <ScrollArea class="h-64">
      <div v-if="loading" class="space-y-2 pr-3">
        <div v-for="i in 5" :key="i" class="h-9 animate-pulse rounded-md bg-muted" />
      </div>
      <div v-else class="space-y-2 pr-3">
        <div v-for="log in logs.slice(0, 12)" :key="log.task_id" class="grid grid-cols-[70px_1fr_auto] items-center gap-2 rounded-md border border-border bg-muted/20 px-3 py-2 text-xs">
          <span class="font-mono text-muted-foreground">{{ fmt(log.created_at) }}</span>
          <span class="truncate">{{ log.command_type || log.task_id }}</span>
          <Badge :variant="variant(log.status)">{{ log.status }}</Badge>
        </div>
        <div v-if="!logs.length" class="rounded-md border border-border bg-muted/30 p-3 text-sm text-muted-foreground">暂无任务日志</div>
      </div>
    </ScrollArea>
  </Card>
</template>
