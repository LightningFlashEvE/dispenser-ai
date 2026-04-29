<script setup lang="ts">
import { cn } from '@/lib/utils'

defineProps<{ class?: string }>()
</script>

<template>
  <div :class="cn('flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card p-3', $props.class)">
    <div v-if="$slots.default" class="flex min-w-0 flex-1 flex-wrap items-center gap-2">
      <slot />
    </div>
    <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>
