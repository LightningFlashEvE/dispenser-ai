<template>
  <div class="page">
    <div class="page-header">
      <div class="page-title-block">
        <h1 class="page-title">配方管理</h1>
        <span class="page-subtitle">{{ formulasStore.formulas.length }} 条配方</span>
      </div>
      <div class="page-actions">
        <el-input v-model="searchQ" placeholder="搜索配方名称 / ID..." clearable style="width:240px" />
        <el-button type="primary" @click="openCreate">+ 新增配方</el-button>
        <el-button @click="formulasStore.fetchAll()">刷新</el-button>
      </div>
    </div>
    <el-alert v-if="formulasStore.error" :title="formulasStore.error" type="error" show-icon style="margin:0 20px 12px" />
    <div class="table-wrap">
      <el-table v-loading="formulasStore.loading" :data="displayFormulas" row-key="formula_id" stripe height="100%" style="width:100%">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="steps-expand">
              <div v-if="!row.steps?.length" class="steps-empty">暂无步骤</div>
              <div v-else class="steps-list">
                <div v-for="step in sortedSteps(row.steps)" :key="step.id" class="step-item">
                  <span class="step-idx">{{ step.step_index }}</span>
                  <span class="step-type">{{ step.command_type }}</span>
                  <span v-if="step.reagent_code" class="step-reagent">{{ step.reagent_code }}</span>
                  <span v-if="step.target_mass_mg" class="step-mass">
                    {{ step.target_mass_mg.toLocaleString() }} mg<span v-if="step.tolerance_mg" class="step-tol"> ±{{ step.tolerance_mg }}</span>
                  </span>
                  <span v-if="step.target_vessel" class="step-vessel">→ {{ step.target_vessel }}</span>
                  <span v-if="step.step_name" class="step-name">{{ step.step_name }}</span>
                </div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="formula_id" label="配方 ID" width="130" />
        <el-table-column prop="formula_name" label="配方名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="别名" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-for="a in row.aliases_list" :key="a" class="badge">{{ a }}</span>
            <span v-if="!row.aliases_list?.length" class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="步骤数" width="80" align="center">
          <template #default="{ row }"><span class="badge badge--blue">{{ row.steps?.length ?? 0 }}</span></template>
        </el-table-column>
        <el-table-column label="更新时间" width="160" prop="updated_at" sortable>
          <template #default="{ row }">{{ fmtDate(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right" align="center">
          <template #default="{ row }">
            <el-button-group size="small">
              <el-button @click="openEdit(row)">编辑</el-button>
              <el-button type="danger" @click="confirmDelete(row)">删除</el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="editingFormula ? '编辑配方' : '新增配方'" width="780px" :close-on-click-modal="false" draggable>
      <el-form ref="formRef" :model="formData" :rules="formRules" label-width="90px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="配方 ID" prop="formula_id">
              <el-input v-model="formData.formula_id" :disabled="!!editingFormula" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="配方名称" prop="formula_name">
              <el-input v-model="formData.formula_name" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="别名">
          <el-select v-model="formData.aliases_list" multiple filterable allow-create placeholder="输入后回车添加" />
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="formData.notes" type="textarea" :rows="2" /></el-form-item>
        <div class="steps-section">
          <div class="steps-section-header">
            <span class="steps-section-title">执行步骤</span>
            <el-button size="small" @click="addStep">+ 添加步骤</el-button>
          </div>
          <div v-if="formData.steps.length === 0" class="steps-section-empty">暂无步骤，点击"添加步骤"</div>
          <div v-for="(step, i) in formData.steps" :key="i" class="step-editor">
            <div class="step-editor-head">
              <span class="step-editor-idx">步骤 {{ step.step_index }}</span>
              <el-input v-model="step.step_name" placeholder="步骤名称（可选）" style="flex:1;max-width:200px" size="small" />
              <el-button type="danger" size="small" circle @click="removeStep(i)">✕</el-button>
            </div>
            <div class="step-editor-body">
              <el-select v-model="step.command_type" style="width:130px" size="small">
                <el-option label="配料 dispense" value="dispense" /><el-option label="分液 aliquot" value="aliquot" />
                <el-option label="混合 mix" value="mix" /><el-option label="补货 restock" value="restock" />
                <el-option label="等待 wait" value="wait" /><el-option label="其他 custom" value="custom" />
              </el-select>
              <el-input v-model="step.reagent_code" placeholder="药品编号" style="width:120px" size="small" />
              <el-input-number v-model="step.target_mass_mg" :min="0" placeholder="目标质量(mg)" style="width:150px" size="small" />
              <el-input-number v-model="step.tolerance_mg" :min="0" placeholder="允差(mg)" style="width:110px" size="small" />
              <el-input v-model="step.target_vessel" placeholder="容器/工位" style="width:100px" size="small" />
            </div>
          </div>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { useFormulasStore } from '@/stores/formulas'
import type { Formula, FormulaCreate, FormulaUpdate, FormulaStepInput, FormulaStep } from '@/services/api'

const formulasStore = useFormulasStore()
onMounted(() => formulasStore.fetchAll())

const searchQ = ref('')
const displayFormulas = computed(() => {
  const q = searchQ.value.trim().toLowerCase()
  if (!q) return formulasStore.formulas
  return formulasStore.formulas.filter((f) =>
    f.formula_id.toLowerCase().includes(q) || f.formula_name.toLowerCase().includes(q) ||
    f.aliases_list.some((a) => a.toLowerCase().includes(q)))
})
function sortedSteps(steps: FormulaStep[]) { return [...steps].sort((a, b) => a.step_index - b.step_index) }

const dialogVisible = ref(false)
const editingFormula = ref<Formula | null>(null)
const saving = ref(false)
const formRef = ref<FormInstance | null>(null)
interface FormModel { formula_id: string; formula_name: string; aliases_list: string[]; notes: string | null; steps: FormulaStepInput[] }
const formData = reactive<FormModel>({ formula_id: '', formula_name: '', aliases_list: [], notes: null, steps: [] })
const formRules: FormRules = {
  formula_id:   [{ required: true, message: '请输入配方 ID',   trigger: 'blur' }],
  formula_name: [{ required: true, message: '请输入配方名称', trigger: 'blur' }],
}
function resetForm() { Object.assign(formData, { formula_id: '', formula_name: '', aliases_list: [], notes: null, steps: [] }) }
function openCreate() { editingFormula.value = null; resetForm(); dialogVisible.value = true }
function openEdit(formula: Formula) {
  editingFormula.value = formula
  Object.assign(formData, {
    formula_id: formula.formula_id, formula_name: formula.formula_name,
    aliases_list: [...formula.aliases_list], notes: formula.notes,
    steps: formula.steps.map((s) => ({ step_index: s.step_index, step_name: s.step_name,
      command_type: s.command_type, reagent_code: s.reagent_code,
      target_mass_mg: s.target_mass_mg, tolerance_mg: s.tolerance_mg, target_vessel: s.target_vessel })),
  })
  dialogVisible.value = true
}
function addStep() {
  const nextIdx = formData.steps.length > 0 ? Math.max(...formData.steps.map((s) => s.step_index)) + 1 : 1
  formData.steps.push({ step_index: nextIdx, step_name: null, command_type: 'dispense', reagent_code: null, target_mass_mg: null, tolerance_mg: null, target_vessel: null })
}
function removeStep(i: number) { formData.steps.splice(i, 1); formData.steps.forEach((s, idx) => { s.step_index = idx + 1 }) }
async function submitForm() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    if (editingFormula.value) {
      await formulasStore.update(editingFormula.value.formula_id, { formula_name: formData.formula_name, aliases_list: formData.aliases_list, notes: formData.notes, steps: formData.steps } as FormulaUpdate)
      ElMessage.success('配方已更新')
    } else {
      await formulasStore.create({ formula_id: formData.formula_id, formula_name: formData.formula_name, aliases_list: formData.aliases_list, notes: formData.notes, steps: formData.steps } as FormulaCreate)
      ElMessage.success('配方已添加')
    }
    dialogVisible.value = false
  } catch (e: unknown) { ElMessage.error(e instanceof Error ? e.message : '操作失败') }
  finally { saving.value = false }
}
async function confirmDelete(formula: Formula) {
  await ElMessageBox.confirm(`确认删除配方「${formula.formula_name}」？`, '确认删除', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  try { await formulasStore.remove(formula.formula_id); ElMessage.success('已删除') }
  catch (e: unknown) { ElMessage.error(e instanceof Error ? e.message : '删除失败') }
}
function fmtDate(iso: string) {
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.page-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--wf-border-dark); flex-shrink: 0; gap: 16px; flex-wrap: wrap; }
.page-title-block { display: flex; align-items: baseline; gap: 10px; }
.page-title { font-size: 32px; font-weight: 500; color: var(--wf-text-main); letter-spacing: -0.5px; }
.page-subtitle { font-size: 14px; color: var(--wf-text-muted); font-weight: 500; }
.page-actions { display: flex; align-items: center; gap: 8px; }
.table-wrap { flex: 1; overflow: hidden; padding: 0 20px 20px; margin-top: 16px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; background: #f0f0f0; color: var(--wf-text-muted); margin-right: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.badge--blue { background: rgba(20, 110, 245, 0.1); color: var(--wf-blue); }
.text-muted { color: var(--wf-text-muted); font-size: 13px; }
.steps-expand { padding: 12px 20px 12px 56px; }
.steps-empty { color: var(--wf-text-muted); font-size: 13px; font-style: italic; }
.steps-list { display: flex; flex-direction: column; gap: 6px; }
.step-item { display: flex; align-items: center; gap: 10px; font-size: 13px; padding: 6px 10px; background: #f8f8f8; border-radius: 4px; border: 1px solid var(--wf-border-dark); }
.step-idx { width: 24px; height: 24px; border-radius: 50%; background: var(--wf-blue); color: var(--wf-white); display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; }
.step-type { font-weight: 600; color: var(--wf-text-main); min-width: 80px; }
.step-reagent { color: var(--wf-purple); font-family: var(--wf-font-mono); font-size: 12px; background: rgba(122, 61, 255, 0.1); padding: 2px 6px; border-radius: 3px; }
.step-mass { color: var(--wf-text-main); font-weight: 500; }
.step-tol { color: var(--wf-text-muted); font-size: 11px; }
.step-vessel { color: var(--wf-text-muted); }
.step-name { color: var(--wf-text-muted); font-style: italic; margin-left: auto; }
.steps-section { margin-top: 16px; border: 1px solid var(--wf-border-dark); border-radius: 6px; overflow: hidden; }
.steps-section-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: var(--wf-bg-panel); border-bottom: 1px solid var(--wf-border-dark); }
.steps-section-title { font-size: 13px; font-weight: 600; color: var(--wf-text-main); }
.steps-section-empty { padding: 16px 12px; color: var(--wf-text-muted); font-size: 13px; text-align: center; }
.step-editor { border-bottom: 1px solid #f0f0f0; padding: 10px 12px; }
.step-editor:last-child { border-bottom: none; }
.step-editor-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.step-editor-idx { font-size: 12px; font-weight: 700; color: var(--wf-blue); min-width: 40px; }
.step-editor-body { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
</style>
