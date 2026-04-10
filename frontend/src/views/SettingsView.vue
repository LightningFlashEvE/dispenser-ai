<template>
  <div class="view-container">
    <div class="page-header">
      <h2>系统设置</h2>
      <div class="actions">
        <el-button type="primary">保存更改</el-button>
      </div>
    </div>
    
    <el-card class="content-card">
      <div class="empty-state">设置面板开发中</div>
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
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-state {
  color: var(--text-secondary);
  font-size: 1.1rem;
}
</style>
