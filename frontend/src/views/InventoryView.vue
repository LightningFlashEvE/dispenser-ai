<template>
  <div class="page">
    <div class="page-header">
      <div class="page-title-block">
        <h1 class="page-title">药品库存</h1>
        <span class="page-subtitle">{{ inventoryStore.drugs.length }} 条记录</span>
      </div>
      <div class="page-actions">
        <el-input v-model="searchQ" placeholder="搜索药品名称 / 编号 / 别名..." clearable style="width:280px" />
        <el-button type="primary" @click="openCreate">+ 新增药品</el-button>
        <el-button @click="inventoryStore.fetchAll()">刷新</el-button>
      </div>
    </div>

    <el-alert v-if="inventoryStore.error" :title="inventoryStore.error" type="error" show-icon style="margin:0 20px 12px" />

    <div class="table-wrap wf-table-shell">
      <el-table class="wf-data-table" v-loading="inventoryStore.loading" :data="displayDrugs" row-key="reagent_code" stripe height="100%" style="width:100%">
        <el-table-column prop="reagent_code" label="编号" width="100" fixed />
        <el-table-column prop="reagent_name_cn" label="中文名" min-width="140" show-overflow-tooltip />
        <el-table-column prop="reagent_name_formula" label="化学式" width="110" show-overflow-tooltip />
        <el-table-column prop="purity_grade" label="纯度" width="80" align="center">
          <template #default="{ row }">
            <span v-if="row.purity_grade" class="badge">{{ row.purity_grade }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="station_id" label="工位" width="70" align="center">
          <template #default="{ row }">
            <span v-if="row.station_id" class="badge badge--blue">{{ row.station_id }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="stock_mg" label="库存 (mg)" width="120" align="right" sortable>
          <template #default="{ row }">
            <span :class="row.stock_mg < 1000 ? 'stock-low' : 'stock-ok'">{{ row.stock_mg.toLocaleString() }}</span>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="160" prop="updated_at" sortable>
          <template #default="{ row }">{{ fmtDate(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right" align="center">
          <template #default="{ row }">
            <el-button-group size="small">
              <el-button @click="openEdit(row)">编辑</el-button>
              <el-button @click="openStockAdj(row)">调库存</el-button>
              <el-button type="danger" @click="confirmDelete(row)">删除</el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="editingDrug ? '编辑药品' : '新增药品'" width="620px" :close-on-click-modal="false" draggable>
      <el-form ref="formRef" :model="formData" :rules="formRules" label-width="110px">
        <el-form-item label="药品编号" prop="reagent_code" v-if="!editingDrug">
          <el-input v-model="formData.reagent_code" placeholder="唯一编号" />
        </el-form-item>
        <el-form-item label="中文名" prop="reagent_name_cn"><el-input v-model="formData.reagent_name_cn" /></el-form-item>
        <el-form-item label="英文名"><el-input v-model="formData.reagent_name_en" /></el-form-item>
        <el-form-item label="化学式"><el-input v-model="formData.reagent_name_formula" /></el-form-item>
        <el-form-item label="CAS 号"><el-input v-model="formData.cas_number" /></el-form-item>
        <el-form-item label="纯度等级">
          <el-select v-model="formData.purity_grade" clearable>
            <el-option label="分析纯 (AR)" value="AR" /><el-option label="化学纯 (CP)" value="CP" />
            <el-option label="优级纯 (GR)" value="GR" /><el-option label="生化试剂 (BR)" value="BR" />
            <el-option label="医药级" value="pharmaceutical" />
          </el-select>
        </el-form-item>
        <el-form-item label="工位 ID"><el-input v-model="formData.station_id" style="width:120px" /></el-form-item>
        <el-form-item label="初始库存 (mg)" v-if="!editingDrug">
          <el-input-number v-model="formData.stock_mg" :min="0" :step="1000" />
        </el-form-item>
        <el-form-item label="摩尔质量"><el-input v-model.number="formData.molar_weight_g_mol" placeholder="g/mol" style="width:140px" /></el-form-item>
        <el-form-item label="别名">
          <el-select v-model="formData.aliases_list" multiple filterable allow-create placeholder="输入后回车添加" />
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="formData.notes" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="stockDialogVisible" title="调整库存" width="400px" :close-on-click-modal="false">
      <div v-if="adjTarget" class="stock-adj-info">
        <div class="adj-name">{{ adjTarget.reagent_name_cn }}</div>
        <div class="adj-current">当前库存：<strong>{{ adjTarget.stock_mg.toLocaleString() }} mg</strong></div>
      </div>
      <el-form label-width="80px" style="margin-top:16px">
        <el-form-item label="调整量">
          <el-input-number v-model="adjDelta" :step="100" style="width:200px" />
          <span style="margin-left:8px; color:#888; font-size:13px">mg</span>
        </el-form-item>
        <el-form-item label="调整后">
          <span :class="adjDelta + (adjTarget?.stock_mg ?? 0) < 0 ? 'stock-low' : 'stock-ok'" style="font-size:15px;font-weight:600">
            {{ ((adjTarget?.stock_mg ?? 0) + adjDelta).toLocaleString() }} mg
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="stockDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving"
          :disabled="adjDelta === 0 || (adjTarget?.stock_mg ?? 0) + adjDelta < 0"
          @click="submitStockAdj">确认调整</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { useInventoryStore } from '@/stores/inventory'
import type { Drug, DrugCreate, DrugUpdate } from '@/services/api'

const inventoryStore = useInventoryStore()
onMounted(() => inventoryStore.fetchAll())

const searchQ = ref('')
const displayDrugs = computed(() => {
  const q = searchQ.value.trim().toLowerCase()
  if (!q) return inventoryStore.drugs
  return inventoryStore.drugs.filter((d) =>
    d.reagent_code.toLowerCase().includes(q) || d.reagent_name_cn.toLowerCase().includes(q) ||
    (d.reagent_name_en?.toLowerCase().includes(q) ?? false) ||
    (d.reagent_name_formula?.toLowerCase().includes(q) ?? false) ||
    d.aliases_list.some((a) => a.toLowerCase().includes(q)))
})

const dialogVisible = ref(false)
const editingDrug = ref<Drug | null>(null)
const saving = ref(false)
const formRef = ref<FormInstance | null>(null)
const formData = reactive<DrugCreate & { stock_mg: number }>({
  reagent_code: '', reagent_name_cn: '', reagent_name_en: null, reagent_name_formula: null,
  cas_number: null, purity_grade: null, molar_weight_g_mol: null, density_g_cm3: null,
  station_id: null, stock_mg: 0, notes: null, aliases_list: [],
})
const formRules: FormRules = {
  reagent_code: [{ required: true, message: '请输入药品编号', trigger: 'blur' }],
  reagent_name_cn: [{ required: true, message: '请输入中文名', trigger: 'blur' }],
}
function resetForm() {
  Object.assign(formData, { reagent_code: '', reagent_name_cn: '', reagent_name_en: null,
    reagent_name_formula: null, cas_number: null, purity_grade: null, molar_weight_g_mol: null,
    density_g_cm3: null, station_id: null, stock_mg: 0, notes: null, aliases_list: [] })
}
function openCreate() { editingDrug.value = null; resetForm(); dialogVisible.value = true }
function openEdit(drug: Drug) {
  editingDrug.value = drug
  Object.assign(formData, { ...drug, aliases_list: [...drug.aliases_list] })
  dialogVisible.value = true
}
async function submitForm() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    if (editingDrug.value) {
      const u: DrugUpdate = { reagent_name_cn: formData.reagent_name_cn, reagent_name_en: formData.reagent_name_en,
        reagent_name_formula: formData.reagent_name_formula, cas_number: formData.cas_number,
        purity_grade: formData.purity_grade, molar_weight_g_mol: formData.molar_weight_g_mol,
        density_g_cm3: formData.density_g_cm3, station_id: formData.station_id,
        notes: formData.notes, aliases_list: formData.aliases_list }
      await inventoryStore.update(editingDrug.value.reagent_code, u)
      ElMessage.success('药品信息已更新')
    } else {
      await inventoryStore.create({ ...formData }); ElMessage.success('药品已添加')
    }
    dialogVisible.value = false
  } catch (e: unknown) { ElMessage.error(e instanceof Error ? e.message : '操作失败') }
  finally { saving.value = false }
}
async function confirmDelete(drug: Drug) {
  await ElMessageBox.confirm(`确认删除药品「${drug.reagent_name_cn}」？此操作为软删除。`, '确认删除',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  try { await inventoryStore.remove(drug.reagent_code); ElMessage.success('已删除') }
  catch (e: unknown) { ElMessage.error(e instanceof Error ? e.message : '删除失败') }
}

const stockDialogVisible = ref(false)
const adjTarget = ref<Drug | null>(null)
const adjDelta = ref(0)
function openStockAdj(drug: Drug) { adjTarget.value = drug; adjDelta.value = 0; stockDialogVisible.value = true }
async function submitStockAdj() {
  if (!adjTarget.value || adjDelta.value === 0) return
  saving.value = true
  try {
    await inventoryStore.adjustStock(adjTarget.value.reagent_code, adjDelta.value)
    ElMessage.success(`库存已调整 ${adjDelta.value > 0 ? '+' : ''}${adjDelta.value} mg`)
    stockDialogVisible.value = false
  } catch (e: unknown) { ElMessage.error(e instanceof Error ? e.message : '调整失败') }
  finally { saving.value = false }
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
.page-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.table-wrap { flex: 1; overflow: hidden; padding: 0 20px 20px; margin-top: 16px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; background: rgba(255,255,255,0.06); color: var(--wf-text-soft); text-transform: uppercase; letter-spacing: 0.5px; }
.badge--blue { background: rgba(20, 110, 245, 0.1); color: var(--wf-blue); }
.stock-low { color: var(--wf-red); font-weight: 600; }
.stock-ok  { color: var(--wf-text-main); }
.text-muted { color: var(--wf-text-muted); }
.stock-adj-info { padding: 12px 0 0; }
.adj-name { font-size: 16px; font-weight: 600; color: var(--wf-text-main); margin-bottom: 6px; }
.adj-current { font-size: 14px; color: var(--wf-text-muted); }
</style>
