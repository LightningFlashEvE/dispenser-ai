<template>
  <div class="view-container">
    <div class="page-header">
      <h2>工位识别</h2>
      <div class="actions">
        <el-button type="primary">刷新识别</el-button>
      </div>
    </div>
    
    <div class="vision-grid">
      <el-card class="camera-card">
        <div class="camera-placeholder">
          实时画面监控载入中...
        </div>
      </el-card>
      
      <el-card class="stations-card">
        <h3 class="card-title">工位状态图</h3>
        <div class="empty-state">
          等待视觉系统连接
        </div>
      </el-card>
    </div>
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

.vision-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: var(--spacing-4);
  flex: 1;
}

.camera-card {
  display: flex;
  align-items: center;
  justify-content: center;
}

.camera-placeholder {
  color: var(--text-secondary);
  font-size: 1.2rem;
}

.stations-card {
  display: flex;
  flex-direction: column;
}

.card-title {
  margin-bottom: var(--spacing-4);
  font-size: 1.1rem;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}
</style>
