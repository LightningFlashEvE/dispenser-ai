<script setup lang="ts">
import Card from '@/components/ui/card/Card.vue'
import Badge from '@/components/ui/badge/Badge.vue'
import type { Component } from 'vue'

withDefaults(defineProps<{
  title: string
  value: string | number
  detail?: string
  status?: 'ok' | 'warn' | 'danger' | 'info' | 'offline'
  icon?: Component
}>(), {
  detail: '',
  status: 'info',
})
</script>

<template>
  <Card class="p-4">
    <div class="flex items-start justify-between gap-3">
      <div>
        <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{{ title }}</div>
        <div class="mt-3 text-2xl font-semibold tabular-nums text-foreground">{{ value }}</div>
      </div>
      <div v-if="icon" class="rounded-md border border-border bg-muted p-2">
        <component :is="icon" class="h-4 w-4 text-cyan-300" />
      </div>
    </div>
    <div class="mt-3 flex items-center justify-between gap-2">
      <span class="truncate text-xs text-muted-foreground">{{ detail || '暂无补充信息' }}</span>
      <Badge :variant="status">{{ status }}</Badge>
    </div>
  </Card>
</template>
