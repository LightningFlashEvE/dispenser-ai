<template>
  <div class="page">
    <div class="page-header">
      <div class="page-title-block">
        <h1 class="page-title">系统设置</h1>
        <span class="page-subtitle">配置系统参数与偏好设置</span>
      </div>
    </div>
    <div class="settings-body">
      <div class="wf-card placeholder-card">
        <el-icon class="placeholder-icon"><Setting /></el-icon>
        <h3>更多设置项开发中</h3>
        <p>系统资源与设备状态已迁移至独立的“系统状态”页面。</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Setting } from '@element-plus/icons-vue'
</script>

<style scoped>
.page { display: flex; flex-direction: column; height: 100%; overflow-y: auto; background: var(--wf-bg-page); }
.page-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--wf-border-dark); flex-shrink: 0; gap: 16px; flex-wrap: wrap; }
.page-title-block { display: flex; align-items: baseline; gap: 10px; }
.page-title { font-size: 32px; font-weight: 500; color: var(--wf-text-main); letter-spacing: -0.5px; }
.page-subtitle { font-size: 14px; color: var(--wf-text-muted); font-weight: 500; }

.settings-body { 
  display: flex; 
  flex-direction: column; 
  gap: 20px; 
  padding: 24px; 
  max-width: 800px;
}

.placeholder-card {
  padding: 40px;
  border-radius: 12px;
  background: var(--wf-bg-card);
  border: 1px solid var(--wf-border-dark);
  box-shadow: var(--wf-shadow-cascade);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: var(--wf-text-muted);
}

.placeholder-icon {
  font-size: 48px;
  color: var(--wf-text-muted);
  margin-bottom: 16px;
}

.placeholder-card h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--wf-text-main);
  margin: 0 0 8px 0;
}

.placeholder-card p {
  font-size: 14px;
  margin: 0;
}
</style>
