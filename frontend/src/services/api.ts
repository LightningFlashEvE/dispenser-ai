import axios from 'axios'

const http = axios.create({ baseURL: '/', timeout: 15000 })

export interface Drug {
  reagent_code: string; reagent_name_cn: string; reagent_name_en: string | null
  reagent_name_formula: string | null; aliases_list: string[]; cas_number: string | null
  purity_grade: string | null; molar_weight_g_mol: number | null; density_g_cm3: number | null
  station_id: string | null; stock_mg: number; notes: string | null
  is_active: boolean; created_at: string; updated_at: string
}
export interface DrugCreate {
  reagent_code: string; reagent_name_cn: string; reagent_name_en?: string | null
  reagent_name_formula?: string | null; aliases_list?: string[]; cas_number?: string | null
  purity_grade?: string | null; molar_weight_g_mol?: number | null; density_g_cm3?: number | null
  station_id?: string | null; stock_mg?: number; notes?: string | null
}
export type DrugUpdate = Partial<Omit<DrugCreate, 'reagent_code'>>

export interface FormulaStep {
  id: number; formula_id: string; step_index: number; step_name: string | null
  command_type: string; reagent_code: string | null; target_mass_mg: number | null
  tolerance_mg: number | null; target_vessel: string | null
}
export interface FormulaStepInput {
  step_index: number; step_name?: string | null; command_type: string
  reagent_code?: string | null; target_mass_mg?: number | null
  tolerance_mg?: number | null; target_vessel?: string | null
}
export interface Formula {
  formula_id: string; formula_name: string; aliases_list: string[]
  notes: string | null; steps: FormulaStep[]; created_at: string; updated_at: string
}
export interface FormulaCreate {
  formula_id: string; formula_name: string; aliases_list?: string[]
  notes?: string | null; steps?: FormulaStepInput[]
}
export interface FormulaUpdate {
  formula_name?: string | null; aliases_list?: string[] | null
  notes?: string | null; steps?: FormulaStepInput[] | null
}

export interface Task {
  task_id: string; command_id: string | null; command_type: string | null
  operator_id: string | null; status: string; intent_json: string | null
  command_json: string | null; result_json: string | null; error_message: string | null
  started_at: string | null; completed_at: string | null; created_at: string
}

export interface AuditLog {
  id: number; task_id: string | null; event_type: string; operator_id: string | null
  summary: string | null; detail_json: string | null; created_at: string
}

export interface SystemResources {
  cpu: { percent: number; cores: number }
  memory: { used_mb: number; total_mb: number; percent: number }
  gpu: { percent: number; used_mb: number; total_mb: number }
  disk: { used_gb: number; total_gb: number; percent: number }
}

export interface DeviceStatus {
  device_status: string; balance_ready: boolean; current_command_id: string | null
  state_machine_state: string; current_task_id: string | null
}

export const drugApi = {
  list: (p?: { active_only?: boolean; station_id?: string; skip?: number; limit?: number }) =>
    http.get<Drug[]>('/api/drugs', { params: p }).then((r) => r.data),
  search: (q: string, limit = 10) =>
    http.get<Drug[]>('/api/drugs/search', { params: { q, limit } }).then((r) => r.data),
  get: (code: string) => http.get<Drug>(`/api/drugs/${code}`).then((r) => r.data),
  create: (d: DrugCreate) => http.post<Drug>('/api/drugs', d).then((r) => r.data),
  update: (code: string, d: DrugUpdate) => http.put<Drug>(`/api/drugs/${code}`, d).then((r) => r.data),
  delete: (code: string) => http.delete(`/api/drugs/${code}`),
  adjustStock: (code: string, delta_mg: number) =>
    http.patch<Drug>(`/api/drugs/${code}/stock`, null, { params: { delta_mg } }).then((r) => r.data),
}

export const formulaApi = {
  list: (p?: { skip?: number; limit?: number }) =>
    http.get<Formula[]>('/api/formulas', { params: p }).then((r) => r.data),
  search: (q: string, limit = 10) =>
    http.get<Formula[]>('/api/formulas/search', { params: { q, limit } }).then((r) => r.data),
  get: (id: string) => http.get<Formula>(`/api/formulas/${id}`).then((r) => r.data),
  create: (d: FormulaCreate) => http.post<Formula>('/api/formulas', d).then((r) => r.data),
  update: (id: string, d: FormulaUpdate) => http.put<Formula>(`/api/formulas/${id}`, d).then((r) => r.data),
  delete: (id: string) => http.delete(`/api/formulas/${id}`),
}

export const taskApi = {
  list: (p?: { status?: string; operator_id?: string; skip?: number; limit?: number }) =>
    http.get<Task[]>('/api/tasks', { params: p }).then((r) => r.data),
  get: (id: string) => http.get<Task>(`/api/tasks/${id}`).then((r) => r.data),
  cancel: (id: string) => http.patch<Task>(`/api/tasks/${id}/cancel`).then((r) => r.data),
}

export const logApi = {
  list: (p?: { task_id?: string; event_type?: string; operator_id?: string; start_time?: string; end_time?: string; skip?: number; limit?: number }) =>
    http.get<AuditLog[]>('/api/logs', { params: p }).then((r) => r.data),
}

export const deviceApi = {
  status: () => http.get<DeviceStatus>('/api/device/status').then((r) => r.data),
}

export const systemApi = {
  resources: () => http.get<SystemResources>('/api/system/resources').then((r) => r.data),
}
