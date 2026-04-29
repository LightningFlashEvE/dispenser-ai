<script setup lang="ts">
import { cn } from '@/lib/utils'

withDefaults(defineProps<{
  class?: string
  columns?: 'auto' | 'six'
}>(), {
  columns: 'auto',
})
</script>

<template>
  <section :class="cn(columns === 'six' ? 'grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-6' : 'grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4', $props.class)">
    <slot />
  </section>
</template>
