import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface StationStatus {
  station_id: string
  has_bottle: boolean
  reagent_code: string | null
  reagent_name_cn: string | null
  qr_detected: boolean
  last_updated_at: string
}

export interface BalanceReading {
  mass_mg: number
  stable: boolean
  timestamp: string
}

export const useVisionStore = defineStore('vision', () => {
  const stations = ref<StationStatus[]>([])
  const lastUpdatedAt = ref<string | null>(null)
  const balanceReading = ref<BalanceReading | null>(null)

  function updateStations(data: StationStatus[]) {
    stations.value = data
    lastUpdatedAt.value = new Date().toISOString()
  }

  function updateBalance(reading: BalanceReading) {
    balanceReading.value = reading
  }

  return {
    stations,
    lastUpdatedAt,
    balanceReading,
    updateStations,
    updateBalance,
  }
})
