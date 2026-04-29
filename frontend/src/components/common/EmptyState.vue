<script setup lang="ts">
import { Inbox } from 'lucide-vue-next'

withDefaults(defineProps<{
  title?: string
  description?: string
}>(), {
  title: '暂无数据',
  description: '当前没有可显示的记录。',
})
</script>

<template>
  <div class="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/20 px-4 py-10 text-center">
    <Inbox class="h-8 w-8 text-muted-foreground" />
    <div class="mt-3 text-sm font-semibold">{{ title }}</div>
    <div class="mt-1 max-w-sm text-sm text-muted-foreground">{{ description }}</div>
  </div>
</template>
