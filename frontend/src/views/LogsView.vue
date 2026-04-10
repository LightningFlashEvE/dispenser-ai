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
      <el-table :data="[]" style="width: 100%">
        <template #empty>
          <div class="empty-state">暂无日志记录</div>
        </template>
        <el-table-column prop="time" label="时间" width="180" />
        <el-table-column prop="type" label="事件类型" width="120" />
        <el-table-column prop="operator" label="操作员" width="120" />
        <el-table-column prop="detail" label="详情" />
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
