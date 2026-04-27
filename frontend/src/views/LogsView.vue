<template>
  <div class="page">
    <div class="page-header">
      <div class="page-title-block">
        <h1 class="page-title">操作日志</h1>
        <span class="page-subtitle">{{ logs.length }} 条记录</span>
      </div>
      <div class="page-actions">
        <el-select v-model="filterStatus" clearable placeholder="任务状态" style="width:130px">
          <el-option label="执行中" value="EXECUTING" /><el-option label="完成" value="COMPLETED" />
          <el-option label="失败" value="FAILED" /><el-option label="已取消" value="CANCELLED" />
        </el-select>
        <el-button @click="fetchLogs">刷新</el-button>
      </div>
    </div>
    <div class="table-wrap">
      <el-table v-loading="loading" :data="logs" stripe height="100%" style="width:100%">
        <el-table-column prop="task_id" label="任务 ID" width="220" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="90" align="center">
          <template #default="{ row }">
            <span class="status-tag" :class="`status-${row.status?.toLowerCase()}`">{{ row.status }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="command_type" label="指令类型" width="100" />
        <el-table-column prop="operator_id" label="操作员" width="90" />
        <el-table-column prop="command_id" label="命令 ID" width="220" show-overflow-tooltip />
        <el-table-column label="开始时间" width="160">
          <template #default="{ row }">{{ row.started_at ? fmtDate(row.started_at) : '—' }}</template>
        </el-table-column>
        <el-table-column label="完成时间" width="160">
          <template #default="{ row }">{{ row.completed_at ? fmtDate(row.completed_at) : '—' }}</template>
        </el-table-column>
        <el-table-column label="错误信息" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error_message" class="text-error">{{ row.error_message }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { taskApi, type Task } from '@/services/api'
const logs = ref<Task[]>([])
const loading = ref(false)
const filterStatus = ref<string | null>(null)
onMounted(() => fetchLogs())
async function fetchLogs() {
  loading.value = true
  try { logs.value = await taskApi.list({ status: filterStatus.value ?? undefined, limit: 200 }) }
  catch (e) { console.error(e) }
  finally { loading.value = false }
}
function fmtDate(iso: string) {
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.page-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid #d8d8d8; flex-shrink: 0; gap: 16px; }
.page-title-block { display: flex; align-items: baseline; gap: 10px; }
.page-title { font-size: 20px; font-weight: 600; color: var(--wf-text-main); }
.page-subtitle { font-size: 13px; color: #888; }
.page-actions { display: flex; align-items: center; gap: 8px; }
.table-wrap { flex: 1; overflow: hidden; padding: 0 20px 20px; }
.text-muted { color: #ababab; }
.text-error { color: #ee1d36; font-size: 13px; }
.status-tag { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: 600; text-transform: uppercase; background: #f0f0f0; color: var(--wf-text-muted); }
.status-completed { background: #e8fff0; color: #00a81a; }
.status-failed    { background: #ffe8e8; color: #ee1d36; }
.status-cancelled { background: #f0f0f0; color: var(--wf-text-muted); }
.status-executing { background: #eef0ff; color: #7a3dff; }
</style>
