<script setup lang="ts">
import { AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogOverlay, AlertDialogPortal, AlertDialogRoot, AlertDialogTitle, AlertDialogTrigger } from 'radix-vue'
import Button from '@/components/ui/button/Button.vue'

withDefaults(defineProps<{
  title: string
  description: string
  confirmText?: string
  cancelText?: string
  destructive?: boolean
}>(), {
  confirmText: '确认',
  cancelText: '取消',
  destructive: false,
})
const emit = defineEmits<{ confirm: [] }>()
</script>

<template>
  <AlertDialogRoot>
    <AlertDialogTrigger as-child><slot name="trigger" /></AlertDialogTrigger>
    <AlertDialogPortal>
      <AlertDialogOverlay class="fixed inset-0 z-50 bg-black/75" />
      <AlertDialogContent class="fixed left-1/2 top-1/2 z-50 grid w-[min(92vw,520px)] -translate-x-1/2 -translate-y-1/2 gap-4 rounded-lg border border-border bg-popover p-6 text-popover-foreground shadow-panel">
        <AlertDialogTitle class="text-base font-semibold">{{ title }}</AlertDialogTitle>
        <AlertDialogDescription class="text-sm leading-6 text-muted-foreground">
          {{ description }}
        </AlertDialogDescription>
        <div class="flex justify-end gap-2">
          <AlertDialogCancel as-child>
            <Button variant="outline">{{ cancelText }}</Button>
          </AlertDialogCancel>
          <AlertDialogAction as-child @click="emit('confirm')">
            <Button :variant="destructive ? 'destructive' : 'default'">{{ confirmText }}</Button>
          </AlertDialogAction>
        </div>
      </AlertDialogContent>
    </AlertDialogPortal>
  </AlertDialogRoot>
</template>
