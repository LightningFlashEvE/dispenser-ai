<template>
  <div class="view-container">
    <div class="page-header">
      <h2>操作日志</h2>
      <div class="actions">
        <el-button>按日期筛选</el-button>
        <el-button>导出</el-button>
      </div>
    </div>
    
    <el-card class="content-card">
      <el-table v-loading="loading" :data="logs" style="width: 100%" stripe border size="large">
        <template #empty>
          <div class="empty-state">暂无日志记录</div>
        </template>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="event_type" label="事件类型" width="150" />
        <el-table-column prop="operator_id" label="操作员" width="120" />
        <el-table-column prop="task_id" label="关联任务" width="300" />
        <el-table-column prop="detail" label="详情" />
        <el-table-column prop="created_at" label="时间" width="200" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { logsApi, type AuditLog } from '@/services/api'
import { ElMessage } from 'element-plus'

const logs = ref<AuditLog[]>([])
const loading = ref(false)

const loadData = async () => {
  loading.value = true
  try {
    const { data } = await logsApi.list()
    logs.value = data
  } catch (err) {
    ElMessage.error('加载日志数据失败')
    console.error(err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.view-container {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
  height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.content-card {
  flex: 1;
}

.empty-state {
  padding: var(--spacing-6);
  color: var(--text-secondary);
  text-align: center;
}
</style>
