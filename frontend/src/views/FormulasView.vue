<template>
  <div class="view-container">
    <div class="page-header">
      <h2>配方库</h2>
      <div class="actions">
        <el-button type="primary">创建配方</el-button>
      </div>
    </div>
    
    <el-card class="content-card">
      <el-table v-loading="loading" :data="formulas" style="width: 100%" stripe border size="large">
        <template #empty>
          <div class="empty-state">暂无配方数据</div>
        </template>
        <el-table-column prop="formula_id" label="配方ID" width="180" />
        <el-table-column prop="formula_name" label="配方名称" width="250" />
        <el-table-column prop="created_at" label="创建时间" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default>
            <el-button link type="primary" size="large">详情</el-button>
            <el-button link type="primary" size="large">应用</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { formulaApi, type Formula } from '@/services/api'
import { ElMessage } from 'element-plus'

const formulas = ref<Formula[]>([])
const loading = ref(false)

const loadData = async () => {
  loading.value = true
  try {
    const { data } = await formulaApi.list()
    formulas.value = data
  } catch (err) {
    ElMessage.error('加载配方数据失败')
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
