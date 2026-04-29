<script setup lang="ts">
import { onMounted } from 'vue'
import { useVoiceStore } from '@/stores/voice'
import SidebarNav from '@/components/common/SidebarNav.vue'
import Sonner from '@/components/ui/sonner/Sonner.vue'

const voiceStore = useVoiceStore()

onMounted(() => {
  document.documentElement.classList.add('dark')
  voiceStore.connect()
})
</script>

<template>
  <div class="flex h-screen overflow-hidden bg-background text-foreground">
    <SidebarNav />
    <main class="min-w-0 flex-1 overflow-hidden">
      <router-view />
    </main>
    <Sonner />
  </div>
</template>
