<template>
  <div class="page">
    <div class="page-header">
      <div class="page-title-block">
        <h1 class="page-title">系统状态</h1>
        <span class="page-subtitle">实时资源与设备运行监控</span>
      </div>
      <div class="page-actions">
        <button class="btn btn--secondary" @click="refreshAll">
          <el-icon><Refresh /></el-icon> 刷新状态
        </button>
      </div>
    </div>
    
    <div class="settings-body">
      <div class="wf-card status-card">
        <div class="card-title">系统资源</div>
        <div v-if="resources" class="res-grid">
          <div class="res-item">
            <span class="res-label">CPU</span>
            <el-progress :percentage="resources.cpu.percent" :stroke-width="8" color="#146ef5" style="flex:1" />
            <span class="res-val">{{ resources.cpu.percent.toFixed(1) }}%  {{ resources.cpu.cores }} 核</span>
          </div>
          <div class="res-item">
            <span class="res-label">内存</span>
            <el-progress :percentage="resources.memory.percent" :stroke-width="8" color="#ff6b00" style="flex:1" />
            <span class="res-val">{{ resources.memory.used_mb.toFixed(0) }} / {{ resources.memory.total_mb.toFixed(0) }} MB</span>
          </div>
          <div class="res-item">
            <span class="res-label">GPU</span>
            <el-progress :percentage="resources.gpu.percent" :stroke-width="8" color="#7a3dff" style="flex:1" />
            <span class="res-val">{{ resources.gpu.percent.toFixed(1) }}%</span>
          </div>
          <div class="res-item">
            <span class="res-label">磁盘</span>
            <el-progress :percentage="resources.disk.percent" :stroke-width="8" color="#00d722" style="flex:1" />
            <span class="res-val">{{ resources.disk.used_gb.toFixed(1) }} / {{ resources.disk.total_gb.toFixed(1) }} GB</span>
          </div>
        </div>
        <div v-else class="res-loading">
          <span class="text-muted">加载资源信息中...</span>
        </div>
      </div>

      <div class="wf-card status-card">
        <div class="card-title">设备状态</div>
        <div v-if="deviceStatus" class="device-info">
          <div class="device-row">
            <span class="device-label">设备状态</span>
            <span class="device-val badge-tint">{{ deviceStatus.device_status }}</span>
          </div>
          <div class="device-row">
            <span class="device-label">状态机</span>
            <span class="device-val badge-tint">{{ deviceStatus.state_machine_state }}</span>
          </div>
          <div class="device-row">
            <span class="device-label">天平就绪</span>
            <span class="device-val badge-solid" :class="deviceStatus.balance_ready ? 'badge-ok' : 'badge-warn'">
              {{ deviceStatus.balance_ready ? '✓ 就绪' : '✗ 未就绪' }}
            </span>
          </div>
          <div class="device-row" v-if="deviceStatus.current_task_id">
            <span class="device-label">当前任务</span>
            <span class="device-val mono badge-tint">{{ deviceStatus.current_task_id }}</span>
          </div>
        </div>
        <div v-else class="res-loading">
          <span class="text-muted">加载设备状态中...</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { systemApi, deviceApi, type SystemResources, type DeviceStatus } from '@/services/api'
import { Refresh } from '@element-plus/icons-vue'

const resources = ref<SystemResources | null>(null)
const deviceStatus = ref<DeviceStatus | null>(null)

onMounted(() => { 
  fetchResources()
  fetchDevice() 
})

async function fetchResources() { 
  try { resources.value = await systemApi.resources() } catch { /* ignore */ } 
}

async function fetchDevice() { 
  try { deviceStatus.value = await deviceApi.status() } catch { /* ignore */ } 
}

function refreshAll() {
  fetchResources()
  fetchDevice()
}
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

.status-card { 
  padding: 24px; 
  border-radius: 12px;
  background: var(--wf-bg-card);
  border: 1px solid var(--wf-border-dark);
  box-shadow: var(--wf-shadow-cascade);
}

.card-title { 
  font-size: 14px; 
  font-weight: 600; 
  color: var(--wf-text-main); 
  letter-spacing: 0.5px; 
  text-transform: uppercase; 
  margin-bottom: 20px; 
}

.res-grid { display: flex; flex-direction: column; gap: 16px; }
.res-item { display: flex; align-items: center; gap: 16px; }
.res-label { width: 50px; font-size: 12px; font-weight: 600; color: var(--wf-text-muted); text-transform: uppercase; letter-spacing: 0.5px; flex-shrink: 0; }
.res-val { font-size: 13px; color: var(--wf-text-muted); font-variant-numeric: tabular-nums; min-width: 140px; }
.res-loading { padding: 12px 0; }
.text-muted { color: var(--wf-text-muted); font-size: 13px; }

.device-info { display: flex; flex-direction: column; gap: 16px; }
.device-row { display: flex; align-items: center; gap: 16px; }
.device-label { width: 80px; font-size: 12px; font-weight: 600; color: var(--wf-text-muted); text-transform: uppercase; letter-spacing: 0.5px; }

.badge-tint { display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 600; background: rgba(20, 110, 245, 0.08); color: var(--wf-blue); }
.badge-solid { display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; color: var(--wf-white); }
.badge-ok { background: var(--wf-green); }
.badge-warn { background: var(--wf-red); }
.mono { font-family: var(--wf-font-mono); }

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}
.btn--secondary {
  background: var(--wf-bg-page);
  border: 1px solid var(--wf-border-dark);
  color: var(--wf-text-main);
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}
.btn--secondary:hover {
  background: #f8f8f8;
  transform: translateY(-1px);
}
</style>
