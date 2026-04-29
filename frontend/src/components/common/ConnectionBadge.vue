<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/components/ui/badge/Badge.vue'
import { connectionStatusDescriptor } from '@/lib/status'

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

const status = computed(() => connectionStatusDescriptor(props.connected, props.error, props.loading))
</script>

<template>
  <Badge :variant="status.tone">
    <span class="mr-1 h-1.5 w-1.5 rounded-full" :class="connected ? 'bg-emerald-300' : 'bg-slate-400'" />
    {{ label }} {{ status.label }}
  </Badge>
</template>
