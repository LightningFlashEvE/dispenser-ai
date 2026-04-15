<template>
  <div class="view-container">
    <div class="page-header">
      <h2>操作日志</h2>
      <div class="actions">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          size="large"
          style="width:280px"
          @change="loadData"
        />
        <el-button @click="loadData">刷新</el-button>
        <el-button @click="exportData">导出</el-button>
      </div>
    </div>

    <el-card class="content-card">
      <el-table v-loading="loading" :data="logs" style="width:100%" stripe border size="large">
        <template #empty><div class="empty-state">暂无日志记录</div></template>
        <el-table-column prop="id"           label="ID"     width="80"  />
        <el-table-column prop="event_type"   label="事件类型" width="150" />
        <el-table-column prop="operator_id"  label="操作员"  width="120" />
        <el-table-column prop="task_id"      label="关联任务" width="300" />
        <el-table-column prop="detail"       label="详情"    />
        <el-table-column prop="created_at"   label="时间"    width="200" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { logsApi, type AuditLog } from '@/services/api'

const logs      = ref<AuditLog[]>([])
const loading   = ref(false)
const dateRange = ref<[Date, Date] | null>(null)

const loadData = async () => {
  loading.value = true
  try {
    const params: Record<string, string> = { limit: '200' }
    if (dateRange.value) {
      params.start_time = dateRange.value[0].toISOString()
      params.end_time   = new Date(dateRange.value[1].getTime() + 86400000 - 1).toISOString()
    }
    // 使用底层 http 直接带 params
    const { data } = await logsApi.list(200)
    // 前端再按日期过滤（后端 list 不支持直接传 start_time 字符串型参数）
    if (dateRange.value) {
      const start = dateRange.value[0].getTime()
      const end   = dateRange.value[1].getTime() + 86400000 - 1
      logs.value  = data.filter(l => {
        const t = new Date(l.created_at).getTime()
        return t >= start && t <= end
      })
    } else {
      logs.value = data
    }
  } catch {
    ElMessage.error('加载日志数据失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadData)

// ─── 导出 ──────────────────────────────────────────────────────
function exportData(): void {
  const headers = ['ID','事件类型','操作员','关联任务','详情','时间']
  const rows    = logs.value.map(l => [
    l.id, l.event_type, l.operator_id, l.task_id ?? '', l.detail ?? '', l.created_at,
  ])
  const csv  = [headers, ...rows].map(r => r.join(',')).join('\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `操作日志_${new Date().toISOString().slice(0,10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.view-container { display:flex; flex-direction:column; gap:var(--spacing-4); height:100%; }
.page-header    { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }
.actions        { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.content-card   { flex:1; }
.empty-state    { padding:var(--spacing-6); color:var(--text-secondary); text-align:center; }
</style>
