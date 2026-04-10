<template>
  <div class="view-container">
    <div class="page-header">
      <h2>库存管理</h2>
      <div class="actions">
        <el-button type="primary">新增物料</el-button>
        <el-button>导出数据</el-button>
      </div>
    </div>
    
    <el-card class="content-card">
      <el-table v-loading="loading" :data="drugs" style="width: 100%" stripe border size="large">
        <template #empty>
          <div class="empty-state">暂无库存数据</div>
        </template>
        <el-table-column prop="reagent_code" label="物料编号" width="180" />
        <el-table-column prop="reagent_name_cn" label="中文名称" width="180" />
        <el-table-column prop="reagent_name_formula" label="化学式" width="180" />
        <el-table-column prop="purity_grade" label="纯度等级" width="120" />
        <el-table-column prop="station_id" label="存放工位" width="120" />
        <el-table-column prop="stock_mg" label="当前库存 (mg)" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default>
            <el-button link type="primary" size="large">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { drugApi, type Drug } from '@/services/api'
import { ElMessage } from 'element-plus'

const drugs = ref<Drug[]>([])
const loading = ref(false)

const loadData = async () => {
  loading.value = true
  try {
    const { data } = await drugApi.list()
    drugs.value = data
  } catch (err) {
    ElMessage.error('加载库存数据失败')
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
