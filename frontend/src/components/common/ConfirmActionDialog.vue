<script setup lang="ts">
import AlertDialog from '@/components/ui/alert-dialog/AlertDialog.vue'

withDefaults(defineProps<{
  actionName: string
  risk: string
  currentState: string
  confirmText?: string
  destructive?: boolean
  disabled?: boolean
}>(), {
  confirmText: '确认执行',
  destructive: false,
  disabled: false,
})
defineEmits<{ confirm: [] }>()
</script>

<template>
  <AlertDialog
    :title="actionName"
    :description="`${risk} 当前状态：${currentState}`"
    :confirm-text="confirmText"
    :destructive="destructive"
    @confirm="$emit('confirm')"
  >
    <template #trigger>
      <span :class="disabled ? 'pointer-events-none opacity-45' : ''">
        <slot />
      </span>
    </template>
  </AlertDialog>
</template>
