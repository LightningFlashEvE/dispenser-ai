<template>
  <div class="view-container">
    <div class="page-header">
      <h2>配方库</h2>
      <div class="actions">
        <el-button type="primary" @click="openAdd">创建配方</el-button>
      </div>
    </div>

    <el-card class="content-card">
      <el-table v-loading="loading" :data="formulas" style="width:100%" stripe border size="large">
        <template #empty><div class="empty-state">暂无配方数据</div></template>
        <el-table-column prop="formula_id"   label="配方ID"   width="200" />
        <el-table-column prop="formula_name" label="配方名称" width="200" />
        <el-table-column label="步骤数" width="90">
          <template #default="{ row }">{{ row.steps?.length ?? 0 }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="large" @click="openDetail(row)">详情</el-button>
            <el-button link type="primary" size="large" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建 / 编辑弹窗 -->
    <el-dialog
      v-model="editVisible"
      :title="isEdit ? '编辑配方' : '创建配方'"
      width="700px"
      destroy-on-close
    >
      <el-form :model="editForm" :rules="editRules" ref="editFormRef" label-width="100px" size="large">
        <el-form-item label="配方ID" prop="formula_id">
          <el-input v-model="editForm.formula_id" :disabled="isEdit" placeholder="全局唯一，如 formula_001" />
        </el-form-item>
        <el-form-item label="配方名称" prop="formula_name">
          <el-input v-model="editForm.formula_name" />
        </el-form-item>
        <el-form-item label="别名（逗号分隔）">
          <el-input v-model="aliasesStr" placeholder="如 标准缓冲液,PBS" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>

      <!-- 步骤列表 -->
      <div class="steps-header">
        <span class="steps-title">步骤列表</span>
        <el-button size="small" @click="addStep">+ 添加步骤</el-button>
      </div>
      <div v-for="(step, i) in editForm.steps" :key="i" class="step-row">
        <div class="step-idx">#{{ i + 1 }}</div>
        <el-form :model="step" inline size="default" class="step-form">
          <el-form-item label="类型">
            <el-select v-model="step.command_type" style="width:110px">
              <el-option v-for="t in stepTypes" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>
          <el-form-item label="步骤名">
            <el-input v-model="step.step_name" style="width:120px" />
          </el-form-item>
          <el-form-item label="药品编号">
            <el-input v-model="step.reagent_code" style="width:110px" placeholder="如 NaCl-AR" />
          </el-form-item>
          <el-form-item label="目标质量(mg)">
            <el-input-number v-model="step.target_mass_mg" :min="1" style="width:110px" />
          </el-form-item>
          <el-form-item label="误差(mg)">
            <el-input-number v-model="step.tolerance_mg" :min="0" style="width:90px" />
          </el-form-item>
          <el-form-item label="目标容器">
            <el-input v-model="step.target_vessel" style="width:80px" placeholder="A1" />
          </el-form-item>
        </el-form>
        <el-button type="danger" link size="small" @click="removeStep(i)">删除</el-button>
      </div>

      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 详情 Drawer -->
    <el-drawer v-model="detailVisible" title="配方详情" size="480px" destroy-on-close>
      <template v-if="detailFormula">
        <el-descriptions :column="1" border size="large">
          <el-descriptions-item label="配方ID">{{ detailFormula.formula_id }}</el-descriptions-item>
          <el-descriptions-item label="名称">{{ detailFormula.formula_name }}</el-descriptions-item>
          <el-descriptions-item label="别名">{{ detailFormula.aliases_list?.join('、') || '—' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detailFormula.created_at }}</el-descriptions-item>
        </el-descriptions>
        <div class="detail-steps-title">步骤明细</div>
        <el-table :data="detailFormula.steps" border size="large" style="margin-top:8px">
          <el-table-column prop="step_index"    label="#"        width="50" />
          <el-table-column prop="step_name"     label="步骤名"   width="100" />
          <el-table-column prop="command_type"  label="类型"     width="90" />
          <el-table-column prop="reagent_code"  label="药品编号" width="110" />
          <el-table-column prop="target_mass_mg" label="目标(mg)" width="90" />
          <el-table-column prop="tolerance_mg"  label="误差(mg)" width="80" />
          <el-table-column prop="target_vessel" label="容器"     width="70" />
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { formulaApi, type Formula, type FormulaStep } from '@/services/api'

const formulas = ref<Formula[]>([])
const loading  = ref(false)

const loadData = async () => {
  loading.value = true
  try {
    const { data } = await formulaApi.list()
    formulas.value = data
  } catch {
    ElMessage.error('加载配方数据失败')
  } finally {
    loading.value = false
  }
}
onMounted(loadData)

// ─── 编辑弹窗 ─────────────────────────────────────────────────
const editVisible  = ref(false)
const isEdit       = ref(false)
const saving       = ref(false)
const editFormRef  = ref<FormInstance>()
const stepTypes    = ['dispense', 'aliquot', 'mix', 'restock']

interface EditForm {
  formula_id: string
  formula_name: string
  notes: string
  steps: Partial<FormulaStep>[]
}

const editForm = reactive<EditForm>({ formula_id: '', formula_name: '', notes: '', steps: [] })
const aliasesStr = ref('')

const editRules: FormRules = {
  formula_id:   [{ required: true, message: '请填写配方ID' }],
  formula_name: [{ required: true, message: '请填写配方名称' }],
}

function emptyStep(index: number): Partial<FormulaStep> {
  return { step_index: index, step_name: '', command_type: 'dispense', reagent_code: '', target_mass_mg: 100, tolerance_mg: 5, target_vessel: '' }
}

function openAdd(): void {
  isEdit.value = false
  editForm.formula_id = ''; editForm.formula_name = ''; editForm.notes = ''
  editForm.steps = []
  aliasesStr.value = ''
  editVisible.value = true
}

function openEdit(row: Formula): void {
  isEdit.value = true
  editForm.formula_id   = row.formula_id
  editForm.formula_name = row.formula_name
  editForm.notes        = (row as Formula & { notes?: string }).notes ?? ''
  editForm.steps        = (row.steps ?? []).map(s => ({ ...s }))
  aliasesStr.value      = (row.aliases_list ?? []).join(', ')
  editVisible.value = true
}

function addStep(): void {
  editForm.steps.push(emptyStep(editForm.steps.length))
}

function removeStep(i: number): void {
  editForm.steps.splice(i, 1)
  editForm.steps.forEach((s, idx) => { s.step_index = idx })
}

async function handleSave(): Promise<void> {
  await editFormRef.value?.validate()
  saving.value = true
  try {
    const payload = {
      formula_id:   editForm.formula_id,
      formula_name: editForm.formula_name,
      notes:        editForm.notes,
      aliases_list: aliasesStr.value ? aliasesStr.value.split(',').map(s => s.trim()).filter(Boolean) : [],
      steps: editForm.steps.map((s, i) => ({
        step_index:    i,
        step_name:     s.step_name ?? '',
        command_type:  s.command_type ?? 'dispense',
        reagent_code:  s.reagent_code ?? undefined,
        target_mass_mg: s.target_mass_mg ?? undefined,
        tolerance_mg:  s.tolerance_mg ?? undefined,
        target_vessel: s.target_vessel ?? undefined,
      })),
    }
    if (isEdit.value) {
      await formulaApi.update(editForm.formula_id, payload)
      ElMessage.success('更新成功')
    } else {
      await formulaApi.create(payload)
      ElMessage.success('创建成功')
    }
    editVisible.value = false
    await loadData()
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? '操作失败'
    ElMessage.error(msg)
  } finally {
    saving.value = false
  }
}

// ─── 详情 Drawer ──────────────────────────────────────────────
const detailVisible = ref(false)
const detailFormula = ref<Formula | null>(null)

async function openDetail(row: Formula): Promise<void> {
  try {
    const { data } = await formulaApi.get(row.formula_id)
    detailFormula.value = data
    detailVisible.value = true
  } catch {
    ElMessage.error('获取配方详情失败')
  }
}
</script>

<style scoped>
.view-container  { display:flex; flex-direction:column; gap:var(--spacing-4); height:100%; }
.page-header     { display:flex; justify-content:space-between; align-items:center; }
.content-card    { flex:1; }
.empty-state     { padding:var(--spacing-6); color:var(--text-secondary); text-align:center; }

.steps-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 16px 0 8px;
}
.steps-title { font-size:0.9rem; font-weight:600; color:var(--text-secondary); }

.step-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px;
  background: var(--bg-card-hover);
  border-radius: var(--radius-sm);
  margin-bottom: 6px;
}
.step-idx { font-weight:600; color:var(--text-secondary); padding-top:6px; width:28px; flex-shrink:0; }
.step-form { flex:1; flex-wrap:wrap; }

.detail-steps-title { font-size:0.9rem; font-weight:600; color:var(--text-secondary); margin-top:16px; }
</style>
