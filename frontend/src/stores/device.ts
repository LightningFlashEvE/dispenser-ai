import { defineStore } from 'pinia'
import { ref } from 'vue'
import { deviceApi } from '@/services/api'

export interface DeviceStatus {
  device_status: string
  balance_ready: boolean
  current_command_id: string | null
  state_machine_state: string
  current_task_id: string | null
}

export const useDeviceStore = defineStore('device', () => {
  const status = ref<DeviceStatus | null>(null)
  const lastFetchAt = ref<string | null>(null)
  const fetchError = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  async function fetchStatus(): Promise<void> {
    try {
      const { data } = await deviceApi.status()
      status.value = data as DeviceStatus
      lastFetchAt.value = new Date().toISOString()
      fetchError.value = null
    } catch {
      fetchError.value = '设备状态获取失败'
    }
  }

  function startPolling(intervalMs = 5000): void {
    if (pollTimer !== null) return
    void fetchStatus()
    pollTimer = setInterval(() => {
      void fetchStatus()
    }, intervalMs)
  }

  function stopPolling(): void {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  return {
    status,
    lastFetchAt,
    fetchError,
    fetchStatus,
    startPolling,
    stopPolling,
  }
})
