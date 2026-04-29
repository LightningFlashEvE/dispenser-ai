<script setup lang="ts">
import Badge from '@/components/ui/badge/Badge.vue'
import Card from '@/components/ui/card/Card.vue'
import type { Component } from 'vue'

defineProps<{
  name: string
  status: 'online' | 'offline' | 'running' | 'warning' | 'error' | 'unknown'
  detail?: string
  icon?: Component
}>()

const statusText: Record<string, string> = {
  online: '在线',
  offline: '离线',
  running: '运行中',
  warning: '警告',
  error: '异常',
  unknown: '未知',
}
const variantMap: Record<string, 'ok' | 'warn' | 'danger' | 'info' | 'offline'> = {
  online: 'ok',
  offline: 'offline',
  running: 'info',
  warning: 'warn',
  error: 'danger',
  unknown: 'offline',
}
</script>

<template>
  <Card class="p-4">
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <div class="rounded-md border border-border bg-muted p-2">
          <component :is="icon" v-if="icon" class="h-4 w-4 text-cyan-300" />
        </div>
        <div>
          <div class="text-sm font-semibold">{{ name }}</div>
          <div class="mt-1 text-xs text-muted-foreground">{{ detail || '无详细状态' }}</div>
        </div>
      </div>
      <Badge :variant="variantMap[status]">{{ statusText[status] }}</Badge>
    </div>
  </Card>
</template>
