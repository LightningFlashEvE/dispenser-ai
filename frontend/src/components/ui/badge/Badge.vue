<script setup lang="ts">
import { computed } from 'vue'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold tabular-nums transition-colors',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-primary/15 text-cyan-200',
        secondary: 'border-border bg-secondary text-secondary-foreground',
        ok: 'border-emerald-400/30 bg-emerald-500/12 text-emerald-300',
        warn: 'border-amber-400/30 bg-amber-500/12 text-amber-300',
        danger: 'border-red-400/30 bg-red-500/12 text-red-300',
        info: 'border-cyan-400/30 bg-cyan-500/12 text-cyan-300',
        offline: 'border-slate-500/30 bg-slate-500/12 text-slate-300',
        outline: 'border-border text-foreground',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

type BadgeVariants = VariantProps<typeof badgeVariants>
const props = withDefaults(defineProps<{ variant?: BadgeVariants['variant']; class?: string }>(), {
  variant: 'default',
})
const classes = computed(() => cn(badgeVariants({ variant: props.variant }), props.class))
</script>

<template>
  <span :class="classes"><slot /></span>
</template>
