<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/components/ui/badge/Badge.vue'

const props = withDefaults(defineProps<{
  label: string
  connected?: boolean
  loading?: boolean
  error?: boolean
}>(), {
  connected: false,
  loading: false,
  error: false,
})

const variant = computed(() => {
  if (props.error) return 'danger'
  if (props.loading) return 'info'
  return props.connected ? 'ok' : 'offline'
})
const text = computed(() => {
  if (props.error) return '异常'
  if (props.loading) return '连接中'
  return props.connected ? '在线' : '离线'
})
</script>

<template>
  <Badge :variant="variant">
    <span class="mr-1 h-1.5 w-1.5 rounded-full" :class="connected ? 'bg-emerald-300' : 'bg-slate-400'" />
    {{ label }} {{ text }}
  </Badge>
</template>
