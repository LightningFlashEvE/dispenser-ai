<script setup lang="ts">
defineProps<{
  eyebrow?: string
  title: string
  description?: string
}>()
</script>

<template>
  <header class="mb-5 flex flex-wrap items-center justify-between gap-4">
    <div>
      <div v-if="eyebrow" class="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">{{ eyebrow }}</div>
      <h1 class="mt-1 text-2xl font-semibold tracking-normal">{{ title }}</h1>
      <p v-if="description" class="mt-1 text-sm text-muted-foreground">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2">
      <slot name="actions" />
    </div>
  </header>
</template>
