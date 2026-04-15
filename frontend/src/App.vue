<template>
  <AppLayout>
    <router-view />
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import AppLayout from './components/common/AppLayout.vue'
import { connectWebSocket, disconnectWebSocket } from '@/services/websocket'
import { useDeviceStore } from '@/stores/device'

const deviceStore = useDeviceStore()

onMounted(() => {
  // 全局启动 WebSocket（断线自动重连已在 websocket.ts 内实现）
  connectWebSocket()
  // 全局启动设备状态轮询，每 5 秒拉取一次
  deviceStore.startPolling(5000)
})

onUnmounted(() => {
  disconnectWebSocket()
  deviceStore.stopPolling()
})
</script>
