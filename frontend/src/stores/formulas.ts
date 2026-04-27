import { defineStore } from 'pinia'
import { ref } from 'vue'
import { formulaApi, type Formula, type FormulaCreate, type FormulaUpdate } from '@/services/api'

export const useFormulasStore = defineStore('formulas', () => {
  const formulas = ref<Formula[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchAll(): Promise<void> {
    loading.value = true; error.value = null
    try { formulas.value = await formulaApi.list({ limit: 200 }) }
    catch (e) { error.value = e instanceof Error ? e.message : '加载失败' }
    finally { loading.value = false }
  }

  async function create(data: FormulaCreate): Promise<Formula> {
    const f = await formulaApi.create(data); formulas.value.unshift(f); return f
  }

  async function update(id: string, data: FormulaUpdate): Promise<Formula> {
    const updated = await formulaApi.update(id, data)
    const idx = formulas.value.findIndex((f) => f.formula_id === id)
    if (idx !== -1) formulas.value[idx] = updated; return updated
  }

  async function remove(id: string): Promise<void> {
    await formulaApi.delete(id); formulas.value = formulas.value.filter((f) => f.formula_id !== id)
  }

  return { formulas, loading, error, fetchAll, create, update, remove }
})
