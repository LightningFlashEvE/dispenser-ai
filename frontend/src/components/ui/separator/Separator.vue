<script setup lang="ts">
import { cn } from '@/lib/utils'
withDefaults(defineProps<{ orientation?: 'horizontal' | 'vertical'; class?: string }>(), {
  orientation: 'horizontal',
})
</script>

<template>
  <div
    role="separator"
    :aria-orientation="orientation"
    :class="cn(orientation === 'vertical' ? 'h-full w-px' : 'h-px w-full', 'bg-border', $props.class)"
  />
</template>
