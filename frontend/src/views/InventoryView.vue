<template>
  <div class="view-container">
    <div class="page-header">
      <h2>库存管理</h2>
      <div class="actions">
        <el-button type="primary" @click="openAdd">新增物料</el-button>
        <el-button @click="exportData">导出数据</el-button>
      </div>
    </div>

    <el-card class="content-card">
      <el-table v-loading="loading" :data="drugs" style="width:100%" stripe border size="large">
        <template #empty>
          <div class="empty-state">暂无库存数据</div>
        </template>
        <el-table-column prop="reagent_code"        label="物料编号"     width="160" />
        <el-table-column prop="reagent_name_cn"     label="中文名称"     width="160" />
        <el-table-column prop="reagent_name_formula" label="化学式"      width="120" />
        <el-table-column prop="purity_grade"        label="纯度等级"     width="100" />
        <el-table-column prop="station_id"          label="存放工位"     width="110" />
        <el-table-column prop="stock_mg"            label="当前库存(mg)" width="130" />
        <el-table-column prop="is_active"           label="状态"         width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="large" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增 / 编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑物料' : '新增物料'"
      width="600px"
      destroy-on-close
    >
      <el-form :model="form" :rules="rules" ref="formRef" label-width="120px" size="large">
        <el-form-item label="物料编号" prop="reagent_code">
          <el-input v-model="form.reagent_code" :disabled="isEdit" placeholder="如 NaCl-AR" />
        </el-form-item>
        <el-form-item label="中文名称" prop="reagent_name_cn">
          <el-input v-model="form.reagent_name_cn" />
        </el-form-item>
        <el-form-item label="英文名称">
          <el-input v-model="form.reagent_name_en" />
        </el-form-item>
        <el-form-item label="化学式">
          <el-input v-model="form.reagent_name_formula" placeholder="如 NaCl" />
        </el-form-item>
        <el-form-item label="CAS 号">
          <el-input v-model="form.cas_number" />
        </el-form-item>
        <el-form-item label="纯度等级">
          <el-input v-model="form.purity_grade" placeholder="如 AR" />
        </el-form-item>
        <el-form-item label="摩尔质量(g/mol)">
          <el-input-number v-model="form.molar_weight_g_mol" :min="0" :precision="4" style="width:100%" />
        </el-form-item>
        <el-form-item label="存放工位">
          <el-input v-model="form.station_id" placeholder="如 station_1" />
        </el-form-item>
        <el-form-item label="当前库存(mg)" prop="stock_mg">
          <el-input-number v-model="form.stock_mg" :min="0" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { drugApi, type Drug } from '@/services/api'

const drugs   = ref<Drug[]>([])
const loading = ref(false)

const loadData = async () => {
  loading.value = true
  try {
    const { data } = await drugApi.list()
    drugs.value = data
  } catch {
    ElMessage.error('加载库存数据失败')
  } finally {
    loading.value = false
  }
}
onMounted(loadData)

// ─── 弹窗 ──────────────────────────────────────────────────────
const dialogVisible = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const formRef = ref<FormInstance>()

const emptyForm = (): Partial<Drug> => ({
  reagent_code: '', reagent_name_cn: '', reagent_name_en: '',
  reagent_name_formula: '', cas_number: '', purity_grade: '',
  molar_weight_g_mol: undefined, station_id: '', stock_mg: 0, notes: '',
})

const form = reactive<Partial<Drug>>(emptyForm())

const rules: FormRules = {
  reagent_code:    [{ required: true, message: '请填写物料编号' }],
  reagent_name_cn: [{ required: true, message: '请填写中文名称' }],
  stock_mg:        [{ required: true, message: '请填写当前库存' }],
}

function openAdd(): void {
  isEdit.value = false
  Object.assign(form, emptyForm())
  dialogVisible.value = true
}

function openEdit(row: Drug): void {
  isEdit.value = true
  Object.assign(form, { ...row })
  dialogVisible.value = true
}

async function handleSave(): Promise<void> {
  await formRef.value?.validate()
  saving.value = true
  try {
    if (isEdit.value) {
      await drugApi.update(form.reagent_code!, form)
      ElMessage.success('更新成功')
    } else {
      await drugApi.create(form)
      ElMessage.success('新增成功')
    }
    dialogVisible.value = false
    await loadData()
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? '操作失败'
    ElMessage.error(msg)
  } finally {
    saving.value = false
  }
}

// ─── 导出 ──────────────────────────────────────────────────────
function exportData(): void {
  const headers = ['物料编号','中文名称','化学式','纯度等级','存放工位','当前库存(mg)','CAS号']
  const rows = drugs.value.map(d => [
    d.reagent_code, d.reagent_name_cn, d.reagent_name_formula ?? '',
    d.purity_grade ?? '', d.station_id ?? '', d.stock_mg, d.cas_number ?? '',
  ])
  const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `库存数据_${new Date().toISOString().slice(0,10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.view-container { display:flex; flex-direction:column; gap:var(--spacing-4); height:100%; }
.page-header { display:flex; justify-content:space-between; align-items:center; }
.content-card { flex:1; }
.empty-state { padding:var(--spacing-6); color:var(--text-secondary); text-align:center; }
</style>
