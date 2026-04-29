<script setup lang="ts">
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle, DialogTrigger } from 'radix-vue'
import { X } from 'lucide-vue-next'
defineProps<{ title?: string; description?: string }>()
</script>

<template>
  <DialogRoot>
    <DialogTrigger as-child><slot name="trigger" /></DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-50 bg-black/70 data-[state=open]:animate-in data-[state=closed]:animate-out" />
      <DialogContent class="fixed left-1/2 top-1/2 z-50 grid w-[min(92vw,520px)] -translate-x-1/2 -translate-y-1/2 gap-4 rounded-lg border border-border bg-popover p-6 text-popover-foreground shadow-panel">
        <div v-if="title || description">
          <DialogTitle v-if="title" class="text-base font-semibold">{{ title }}</DialogTitle>
          <DialogDescription v-if="description" class="mt-1 text-sm text-muted-foreground">{{ description }}</DialogDescription>
        </div>
        <slot />
        <DialogClose class="absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100">
          <X class="h-4 w-4" />
        </DialogClose>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
