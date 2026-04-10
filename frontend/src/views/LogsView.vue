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
      <el-table v-loading="loading" :data="tasks" style="width: 100%" stripe border size="large">
        <template #empty>
          <div class="empty-state">暂无日志记录</div>
        </template>
        <el-table-column prop="task_id" label="任务ID" width="300" />
        <el-table-column prop="command_type" label="命令类型" width="150" />
        <el-table-column prop="status" label="状态" width="120" />
        <el-table-column prop="operator_id" label="操作员" width="120" />
        <el-table-column prop="created_at" label="创建时间" width="200" />
        <el-table-column prop="completed_at" label="完成时间" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { taskApi, type TaskRecord } from '@/services/api'
import { ElMessage } from 'element-plus'

const tasks = ref<TaskRecord[]>([])
const loading = ref(false)

const loadData = async () => {
  loading.value = true
  try {
    const { data } = await taskApi.list()
    tasks.value = data
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
