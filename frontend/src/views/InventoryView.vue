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
      <el-table :data="[]" style="width: 100%">
        <template #empty>
          <div class="empty-state">暂无库存数据</div>
        </template>
        <el-table-column prop="id" label="物料编号" width="180" />
        <el-table-column prop="name" label="物料名称" width="180" />
        <el-table-column prop="stock_mg" label="当前库存 (mg)" />
        <el-table-column prop="location" label="存放位置" />
        <el-table-column label="操作" width="120">
          <template #default>
            <el-button link type="primary" size="small">编辑</el-button>
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
