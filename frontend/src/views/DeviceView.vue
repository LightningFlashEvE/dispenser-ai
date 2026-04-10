<template>
  <div class="view-container">
    <div class="page-header">
      <h2>设备状态</h2>
    </div>
    
    <el-card class="content-card">
      <div class="empty-state">功能开发中</div>
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
  font-size: 1.2rem;
}
</style>
