<script setup lang="ts">
import { AlertTriangle } from 'lucide-vue-next'
import Button from '@/components/ui/button/Button.vue'

defineProps<{
  title?: string
  message: string
  retryLabel?: string
}>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="rounded-lg border border-red-400/25 bg-red-500/10 p-4 text-red-100">
    <div class="flex items-start gap-3">
      <AlertTriangle class="mt-0.5 h-5 w-5 shrink-0" />
      <div class="min-w-0 flex-1">
        <div class="text-sm font-semibold">{{ title || '请求失败' }}</div>
        <div class="mt-1 break-words text-sm text-red-100/80">{{ message }}</div>
      </div>
      <Button v-if="$attrs.onRetry" variant="outline" size="sm" @click="$emit('retry')">
        {{ retryLabel || '重试' }}
      </Button>
    </div>
  </div>
</template>
