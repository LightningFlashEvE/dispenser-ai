<template>
  <div class="page">
    <div class="page-header">
      <div class="page-title-block">
        <h1 class="page-title">试剂瓶管理</h1>
        <span class="page-subtitle">{{ bottlesStore.bottles.length }} 条记录</span>
      </div>
      <div class="page-actions">
        <el-select v-model="statusFilter" placeholder="按状态筛选" clearable style="width:150px">
          <el-option label="空瓶" value="empty" />
          <el-option label="已装填" value="filled" />
          <el-option label="使用中" value="in_use" />
          <el-option label="已用尽" value="depleted" />
          <el-option label="清洗中" value="cleaning" />
        </el-select>
        <el-button type="primary" @click="openCreate">+ 新增试剂瓶</el-button>
        <el-button @click="bottlesStore.fetchAll()">刷新</el-button>
      </div>
    </div>

    <el-alert v-if="bottlesStore.error" :title="bottlesStore.error" type="error" show-icon style="margin:0 20px 12px" />

    <div class="table-wrap wf-table-shell">
      <el-table class="wf-data-table" v-loading="bottlesStore.loading" :data="displayBottles" row-key="bottle_id" stripe height="100%" style="width:100%">
        <el-table-column prop="bottle_id" label="瓶编号" width="100" fixed />
        <el-table-column prop="label" label="标签" min-width="160" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="90" align="center">
          <template #default="{ row }">
            <span :class="statusClass(row.status)">{{ statusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="station_id" label="放置工位" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.station_id" class="badge badge--blue">{{ row.station_id }}</span>
            <span v-else class="text-muted">未放置</span>
          </template>
        </el-table-column>
        <el-table-column prop="volume_ml" label="容量 (mL)" width="110" align="right" />
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

    <el-dialog v-model="dialogVisible" :title="editingBottle ? '编辑试剂瓶' : '新增试剂瓶'" width="460px" :close-on-click-modal="false" draggable>
      <el-form ref="formRef" :model="formData" :rules="formRules" label-width="90px">
        <el-form-item label="瓶编号" prop="bottle_id" v-if="!editingBottle">
          <el-input v-model="formData.bottle_id" placeholder="编号，如 1、A1" />
        </el-form-item>
        <el-form-item label="标签" prop="label">
          <el-input v-model="formData.label" placeholder="如：试剂瓶 1、备用空瓶" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="formData.status">
            <el-option label="空瓶" value="empty" />
            <el-option label="已装填" value="filled" />
            <el-option label="使用中" value="in_use" />
            <el-option label="已用尽" value="depleted" />
            <el-option label="清洗中" value="cleaning" />
          </el-select>
        </el-form-item>
        <el-form-item label="放置工位">
          <el-input v-model="formData.station_id" placeholder="如 ST01，留空为未放置" style="width:140px" />
        </el-form-item>
        <el-form-item label="容量 (mL)">
          <el-input-number v-model="formData.volume_ml" :min="0" :step="50" style="width:160px" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="formData.notes" type="textarea" :rows="2" />
        </el-form-item>
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
import { useBottlesStore } from '@/stores/bottles'
import type { ReagentBottle, ReagentBottleCreate, ReagentBottleUpdate } from '@/services/api'

const bottlesStore = useBottlesStore()
onMounted(() => bottlesStore.fetchAll())

const statusFilter = ref<string | null>(null)

const displayBottles = computed(() => {
  const s = statusFilter.value
  if (!s) return bottlesStore.bottles
  return bottlesStore.bottles.filter((b) => b.status === s)
})

function statusLabel(s: string) {
  const map: Record<string, string> = {
    empty: '空瓶', filled: '已装填', in_use: '使用中', depleted: '已用尽', cleaning: '清洗中',
  }
  return map[s] ?? s
}
function statusClass(s: string) {
  const map: Record<string, string> = {
    empty: 'status-empty', filled: 'status-filled', in_use: 'status-inuse',
    depleted: 'status-depleted', cleaning: 'status-cleaning',
  }
  return `status-badge ${map[s] ?? ''}`
}

const dialogVisible = ref(false)
const editingBottle = ref<ReagentBottle | null>(null)
const saving = ref(false)
const formRef = ref<FormInstance | null>(null)
const formData = reactive<ReagentBottleCreate>({ bottle_id: '', label: '', status: 'empty', station_id: null, reagent_code: null, volume_ml: null, notes: null })
const formRules: FormRules = {
  bottle_id: [{ required: true, message: '请输入瓶编号', trigger: 'blur' }],
  label: [{ required: true, message: '请输入标签', trigger: 'blur' }],
}
function resetForm() { Object.assign(formData, { bottle_id: '', label: '', status: 'empty', station_id: null, reagent_code: null, volume_ml: null, notes: null }) }
function openCreate() { editingBottle.value = null; resetForm(); dialogVisible.value = true }
function openEdit(b: ReagentBottle) {
  editingBottle.value = b
  Object.assign(formData, { bottle_id: b.bottle_id, label: b.label, status: b.status, station_id: b.station_id, reagent_code: b.reagent_code, volume_ml: b.volume_ml, notes: b.notes })
  dialogVisible.value = true
}
async function submitForm() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    if (editingBottle.value) {
      const u: ReagentBottleUpdate = { label: formData.label, status: formData.status, station_id: formData.station_id, volume_ml: formData.volume_ml, notes: formData.notes }
      await bottlesStore.update(editingBottle.value.bottle_id, u)
      ElMessage.success('试剂瓶信息已更新')
    } else {
      await bottlesStore.create({ ...formData }); ElMessage.success('试剂瓶已添加')
    }
    dialogVisible.value = false
  } catch (e: unknown) { ElMessage.error(e instanceof Error ? e.message : '操作失败') }
  finally { saving.value = false }
}
async function confirmDelete(b: ReagentBottle) {
  await ElMessageBox.confirm(`确认删除试剂瓶「${b.label}」？此操作为软删除。`, '确认删除', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  try { await bottlesStore.remove(b.bottle_id); ElMessage.success('已删除') }
  catch (e: unknown) { ElMessage.error(e instanceof Error ? e.message : '删除失败') }
}

function fmtDate(iso: string) {
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
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
.text-muted { color: var(--wf-text-muted); }
.status-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; letter-spacing: 0.5px; }
.status-empty { background: rgba(255,255,255,0.05); color: var(--wf-text-soft); }
.status-filled { background: rgba(34, 197, 94, 0.1); color: #22c55e; }
.status-inuse { background: rgba(20, 110, 245, 0.1); color: var(--wf-blue); }
.status-depleted { background: rgba(234, 179, 8, 0.1); color: #eab308; }
.status-cleaning { background: rgba(168, 85, 247, 0.1); color: #a855f7; }
</style>
