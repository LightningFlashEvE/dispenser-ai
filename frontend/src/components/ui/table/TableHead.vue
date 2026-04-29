<script setup lang="ts">
import { cn } from '@/lib/utils'
defineProps<{ class?: string }>()
</script>

<template><th :class="cn('h-9 px-3 text-left align-middle text-xs font-semibold uppercase tracking-wide text-muted-foreground', $props.class)"><slot /></th></template>
