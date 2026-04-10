<template>
  <div class="view-container">
    <div class="page-header">
      <h2>配方库</h2>
      <div class="actions">
        <el-button type="primary">创建配方</el-button>
      </div>
    </div>
    
    <el-card class="content-card">
      <el-table :data="[]" style="width: 100%">
        <template #empty>
          <div class="empty-state">暂无配方数据</div>
        </template>
        <el-table-column prop="name" label="配方名称" width="200" />
        <el-table-column prop="author" label="创建人" width="120" />
        <el-table-column prop="date" label="更新时间" width="180" />
        <el-table-column prop="desc" label="描述" />
        <el-table-column label="操作" width="150">
          <template #default>
            <el-button link type="primary" size="small">详情</el-button>
            <el-button link type="primary" size="small">应用</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

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
