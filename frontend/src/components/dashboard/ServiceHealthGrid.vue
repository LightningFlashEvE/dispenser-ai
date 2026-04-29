<script setup lang="ts">
import { Bot, Mic, Server, Volume2 } from 'lucide-vue-next'
import DeviceStatusCard from '@/components/dashboard/DeviceStatusCard.vue'

defineProps<{
  websocketOnline: boolean
  backendOnline: boolean
  aiState: string
}>()
</script>

<template>
  <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
    <DeviceStatusCard name="ASR 语音识别" :status="websocketOnline ? 'online' : 'offline'" :detail="websocketOnline ? 'WebSocket 可用' : '等待语音通道恢复'" :icon="Mic" />
    <DeviceStatusCard name="LLM 服务" :status="websocketOnline ? 'running' : 'unknown'" :detail="aiState" :icon="Bot" />
    <DeviceStatusCard name="TTS 语音合成" :status="websocketOnline ? 'online' : 'unknown'" detail="通过语音通道回传音频" :icon="Volume2" />
    <DeviceStatusCard name="后级控制程序" :status="backendOnline ? 'online' : 'offline'" :detail="backendOnline ? '设备状态接口可用' : '设备状态接口不可用'" :icon="Server" />
  </div>
</template>
