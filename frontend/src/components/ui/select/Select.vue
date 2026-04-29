<script setup lang="ts">
import { SelectContent, SelectGroup, SelectItem, SelectItemIndicator, SelectItemText, SelectPortal, SelectRoot, SelectTrigger, SelectValue, SelectViewport } from 'radix-vue'
import { Check, ChevronDown } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

defineProps<{ modelValue?: string; placeholder?: string; options: Array<{ label: string; value: string }>; class?: string }>()
defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <SelectRoot :model-value="modelValue" @update:model-value="$emit('update:modelValue', String($event))">
    <SelectTrigger :class="cn('flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring', $props.class)">
      <SelectValue :placeholder="placeholder" />
      <ChevronDown class="h-4 w-4 opacity-60" />
    </SelectTrigger>
    <SelectPortal>
      <SelectContent class="z-50 min-w-32 overflow-hidden rounded-md border border-border bg-popover text-popover-foreground shadow-panel">
        <SelectViewport class="p-1">
          <SelectGroup>
            <SelectItem
              v-for="option in options"
              :key="option.value"
              :value="option.value"
              class="relative flex cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none data-[highlighted]:bg-accent"
            >
              <span class="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                <SelectItemIndicator><Check class="h-4 w-4" /></SelectItemIndicator>
              </span>
              <SelectItemText>{{ option.label }}</SelectItemText>
            </SelectItem>
          </SelectGroup>
        </SelectViewport>
      </SelectContent>
    </SelectPortal>
  </SelectRoot>
</template>
