<script setup lang="ts">
import { cn } from '@/lib/utils'
defineProps<{ class?: string }>()
</script>

<template><tr :class="cn('border-b border-border transition-colors hover:bg-muted/40', $props.class)"><slot /></tr></template>
