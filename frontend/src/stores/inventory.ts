import { defineStore } from 'pinia'
import { ref } from 'vue'
import { drugApi, type Drug, type DrugCreate, type DrugUpdate } from '@/services/api'

export const useInventoryStore = defineStore('inventory', () => {
  const drugs = ref<Drug[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchAll(activeOnly = true): Promise<void> {
    loading.value = true; error.value = null
    try { drugs.value = await drugApi.list({ active_only: activeOnly, limit: 200 }) }
    catch (e) { error.value = e instanceof Error ? e.message : '加载失败' }
    finally { loading.value = false }
  }

  async function create(data: DrugCreate): Promise<Drug> {
    const drug = await drugApi.create(data); drugs.value.unshift(drug); return drug
  }

  async function update(code: string, data: DrugUpdate): Promise<Drug> {
    const updated = await drugApi.update(code, data)
    const idx = drugs.value.findIndex((d) => d.reagent_code === code)
    if (idx !== -1) drugs.value[idx] = updated; return updated
  }

  async function remove(code: string): Promise<void> {
    await drugApi.delete(code); drugs.value = drugs.value.filter((d) => d.reagent_code !== code)
  }

  async function adjustStock(code: string, delta_mg: number): Promise<Drug> {
    const updated = await drugApi.adjustStock(code, delta_mg)
    const idx = drugs.value.findIndex((d) => d.reagent_code === code)
    if (idx !== -1) drugs.value[idx] = updated; return updated
  }

  return { drugs, loading, error, fetchAll, create, update, remove, adjustStock }
})
