<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'

const props = withDefaults(defineProps<{ modelValue?: number; class?: string; indicatorClass?: string }>(), {
  modelValue: 0,
})
const width = computed(() => `${Math.max(0, Math.min(100, props.modelValue))}%`)
</script>

<template>
  <div :class="cn('relative h-2 w-full overflow-hidden rounded-full bg-secondary', props.class)">
    <div :class="cn('h-full rounded-full bg-primary transition-all', props.indicatorClass)" :style="{ width }" />
  </div>
</template>
