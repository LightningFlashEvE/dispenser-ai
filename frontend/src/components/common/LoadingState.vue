<script setup lang="ts">
withDefaults(defineProps<{ rows?: number }>(), {
  rows: 4,
})
</script>

<template>
  <div class="space-y-3">
    <div v-for="row in rows" :key="row" class="h-10 animate-pulse rounded-md bg-muted" />
  </div>
</template>
