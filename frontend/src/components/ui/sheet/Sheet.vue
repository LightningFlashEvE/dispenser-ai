<script setup lang="ts">
import { DialogClose, DialogContent, DialogOverlay, DialogPortal, DialogRoot, DialogTrigger } from 'radix-vue'
import { X } from 'lucide-vue-next'
</script>

<template>
  <DialogRoot>
    <DialogTrigger as-child><slot name="trigger" /></DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-50 bg-black/65" />
      <DialogContent class="fixed right-0 top-0 z-50 h-full w-[min(92vw,380px)] border-l border-border bg-popover p-5 text-popover-foreground shadow-panel">
        <slot />
        <DialogClose class="absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100">
          <X class="h-4 w-4" />
        </DialogClose>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
