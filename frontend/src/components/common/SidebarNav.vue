<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Activity, AudioWaveform, Boxes, Camera, ClipboardList, FlaskConical, Gauge, LayoutDashboard, ListChecks, Settings, Scale, ScrollText } from 'lucide-vue-next'
import Badge from '@/components/ui/badge/Badge.vue'

const router = useRouter()
const route = useRoute()

const iconMap = {
  LayoutDashboard,
  AudioWaveform,
  Boxes,
  ClipboardList,
  ScrollText,
  Camera,
  FlaskConical,
  Gauge,
  Settings,
  ListChecks,
  Scale,
  Activity,
}

const navRoutes = computed(() =>
  router.getRoutes()
    .filter((item) => item.meta?.label && item.meta?.nav !== false)
    .sort((a, b) => Number(a.meta?.order ?? 99) - Number(b.meta?.order ?? 99)),
)
</script>

<template>
  <aside class="flex h-full w-64 shrink-0 flex-col border-r border-border bg-[#071018]">
    <div class="border-b border-border px-5 py-5">
      <div class="flex items-center gap-3">
        <div class="flex h-9 w-9 items-center justify-center rounded-md border border-cyan-400/40 bg-cyan-400/10">
          <Activity class="h-5 w-5 text-cyan-300" />
        </div>
        <div>
          <div class="text-sm font-semibold tracking-wide text-foreground">Dispenser AI</div>
          <div class="text-xs text-muted-foreground">工业配药控制台</div>
        </div>
      </div>
      <Badge variant="info" class="mt-4">AI Assisted Control</Badge>
    </div>
    <nav class="flex-1 space-y-1 px-3 py-4">
      <router-link
        v-for="item in navRoutes"
        :key="item.path"
        :to="item.path"
        class="flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        :class="route.path === item.path ? 'bg-cyan-400/10 text-cyan-200 ring-1 ring-cyan-400/25' : ''"
      >
        <component :is="iconMap[item.meta?.icon as keyof typeof iconMap] ?? LayoutDashboard" class="h-4 w-4" />
        <span>{{ item.meta?.label }}</span>
      </router-link>
    </nav>
    <div class="border-t border-border px-5 py-4 text-xs leading-5 text-muted-foreground">
      所有设备动作必须经过后端规则和确认流程。
    </div>
  </aside>
</template>
