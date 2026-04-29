<script setup lang="ts">
import Badge from '@/components/ui/badge/Badge.vue'
import Card from '@/components/ui/card/Card.vue'
import type { Task } from '@/services/api'

defineProps<{ alarms: Task[]; loading?: boolean }>()
</script>

<template>
  <Card class="p-4">
    <div class="mb-3 flex items-center justify-between">
      <div class="text-sm font-semibold">最近报警</div>
      <Badge :variant="alarms.length ? 'danger' : 'ok'">{{ alarms.length }}</Badge>
    </div>
    <div v-if="loading" class="space-y-2">
      <div v-for="i in 3" :key="i" class="h-10 animate-pulse rounded-md bg-muted" />
    </div>
    <div v-else-if="!alarms.length" class="rounded-md border border-border bg-muted/30 p-3 text-sm text-muted-foreground">暂无报警或失败任务</div>
    <div v-else class="space-y-2">
      <div v-for="alarm in alarms.slice(0, 5)" :key="alarm.task_id" class="rounded-md border border-red-400/20 bg-red-500/10 p-3">
        <div class="flex items-center justify-between gap-2">
          <span class="truncate text-sm font-medium">{{ alarm.command_type || alarm.task_id }}</span>
          <Badge variant="danger">{{ alarm.status }}</Badge>
        </div>
        <div class="mt-1 truncate text-xs text-red-200/80">{{ alarm.error_message || '后端未返回错误详情' }}</div>
      </div>
    </div>
  </Card>
</template>
