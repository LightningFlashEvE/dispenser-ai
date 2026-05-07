import { defineStore } from 'pinia'
import { ref } from 'vue'
import { bottleApi, type ReagentBottle, type ReagentBottleCreate, type ReagentBottleUpdate } from '@/services/api'

export const useBottlesStore = defineStore('bottles', () => {
  const bottles = ref<ReagentBottle[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchAll(): Promise<void> {
    loading.value = true; error.value = null
    try { bottles.value = await bottleApi.list({ limit: 200 }) }
    catch (e) { error.value = e instanceof Error ? e.message : '加载试剂瓶失败' }
    finally { loading.value = false }
  }

  async function create(data: ReagentBottleCreate): Promise<ReagentBottle> {
    const bottle = await bottleApi.create(data); bottles.value.unshift(bottle); return bottle
  }

  async function update(id: string, data: ReagentBottleUpdate): Promise<ReagentBottle> {
    const updated = await bottleApi.update(id, data)
    const idx = bottles.value.findIndex((b) => b.bottle_id === id)
    if (idx !== -1) bottles.value[idx] = updated; return updated
  }

  async function remove(id: string): Promise<void> {
    await bottleApi.delete(id); bottles.value = bottles.value.filter((b) => b.bottle_id !== id)
  }

  return { bottles, loading, error, fetchAll, create, update, remove }
})
