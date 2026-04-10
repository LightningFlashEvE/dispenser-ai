import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})

export interface Drug {
  reagent_code: string
  reagent_name_cn: string
  reagent_name_en?: string
  reagent_name_formula?: string
  reagent_aliases?: string[]
  cas_number?: string
  purity_grade?: string
  molar_weight_g_mol?: number
  density_g_cm3?: number
  station_id?: string
  stock_mg: number
  notes?: string
}

export interface Formula {
  formula_id: string
  formula_name: string
  aliases?: string[]
  steps: unknown[]
  created_at: string
}

export interface TaskRecord {
  task_id: string
  command_type: string
  status: string
  created_at: string
  completed_at?: string
  result?: unknown
}

export const drugApi = {
  list: () => http.get<Drug[]>('/drugs'),
  get: (code: string) => http.get<Drug>(`/drugs/${code}`),
  create: (data: Partial<Drug>) => http.post<Drug>('/drugs', data),
  update: (code: string, data: Partial<Drug>) => http.put<Drug>(`/drugs/${code}`, data),
  remove: (code: string) => http.delete(`/drugs/${code}`),
  search: (q: string) => http.get<Drug[]>('/drugs/search', { params: { q } }),
}

export const formulaApi = {
  list: () => http.get<Formula[]>('/formulas'),
  get: (id: string) => http.get<Formula>(`/formulas/${id}`),
  search: (q: string) => http.get<Formula[]>('/formulas/search', { params: { q } }),
  create: (data: Partial<Formula>) => http.post<Formula>('/formulas', data),
  update: (id: string, data: Partial<Formula>) => http.put<Formula>(`/formulas/${id}`, data),
  remove: (id: string) => http.delete(`/formulas/${id}`),
}

export const taskApi = {
  list: (limit = 50) => http.get<TaskRecord[]>('/tasks', { params: { limit } }),
  get: (id: string) => http.get<TaskRecord>(`/tasks/${id}`),
}

export const deviceApi = {
  status: () => http.get('/device/status'),
}

export default http
