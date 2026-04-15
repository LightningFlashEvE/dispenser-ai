<template>
  <div class="view-container">
    <div class="page-header">
      <h2>工位识别</h2>
      <div class="actions">
        <el-button type="primary" :loading="refreshing" @click="handleRefresh">刷新识别</el-button>
      </div>
    </div>

    <div class="vision-grid">
      <!-- 左侧：摄像头占位 -->
      <el-card class="camera-card">
        <div class="camera-placeholder">实时画面监控载入中...</div>
      </el-card>

      <!-- 右侧：工位状态 -->
      <el-card class="stations-card">
        <h3 class="card-title">工位状态图</h3>
        <div v-if="stations.length === 0" class="empty-state">
          等待视觉系统连接
        </div>
        <div v-else class="station-list">
          <div
            v-for="s in stations"
            :key="s.station_id"
            class="station-item"
            :class="{ occupied: s.has_bottle }"
          >
            <div class="s-id">{{ s.station_id }}</div>
            <div class="s-status">{{ s.has_bottle ? '有瓶' : '空位' }}</div>
            <div v-if="s.reagent_name_cn" class="s-drug">{{ s.reagent_name_cn }}</div>
            <div v-if="s.qr_detected" class="s-qr">
              <el-tag size="small" type="success">QR ✓</el-tag>
            </div>
            <div class="s-update">{{ formatTime(s.last_updated_at) }}</div>
          </div>
        </div>
        <div v-if="lastUpdatedAt" class="footer-update">
          上次更新: {{ formatTime(lastUpdatedAt) }}
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { useVisionStore } from '@/stores/vision'
import { stationsApi } from '@/services/api'

const visionStore = useVisionStore()
const { stations, lastUpdatedAt } = storeToRefs(visionStore)

const refreshing = ref(false)

async function handleRefresh(): Promise<void> {
  refreshing.value = true
  try {
    const { data } = await stationsApi.list()
    // 后端返回工位列表，更新 store
    visionStore.updateStations(
      (data as unknown[]).map((s: unknown) => {
        const st = s as {
          station_id: string
          has_bottle?: boolean
          reagent_code?: string | null
          reagent_name_cn?: string | null
          qr_detected?: boolean
          last_updated_at?: string
        }
        return {
          station_id:     st.station_id,
          has_bottle:     st.has_bottle ?? false,
          reagent_code:   st.reagent_code ?? null,
          reagent_name_cn: st.reagent_name_cn ?? null,
          qr_detected:    st.qr_detected ?? false,
          last_updated_at: st.last_updated_at ?? new Date().toISOString(),
        }
      })
    )
    ElMessage.success('工位状态已刷新')
  } catch {
    ElMessage.warning('视觉接口暂不可用，展示上次缓存数据')
  } finally {
    refreshing.value = false
  }
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return iso }
}
</script>

<style scoped>
.view-container { display:flex; flex-direction:column; gap:var(--spacing-4); height:100%; }
.page-header    { display:flex; justify-content:space-between; align-items:center; }

.vision-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: var(--spacing-4);
  flex: 1;
  min-height: 0;
}

.camera-card {
  display: flex;
  align-items: center;
  justify-content: center;
}
.camera-placeholder { color:var(--text-secondary); font-size:1.2rem; }

.stations-card { display:flex; flex-direction:column; overflow:hidden; }
.card-title    { margin-bottom:var(--spacing-4); font-size:1.1rem; }

.station-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.station-item {
  display: grid;
  grid-template-columns: 80px 60px 1fr auto;
  align-items: center;
  gap: 8px;
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-sm);
  background: var(--bg-card-hover);
  border: 1px solid var(--border-color);
  font-size: 0.85rem;
}
.station-item.occupied {
  background: rgba(34,197,94,0.08);
  border-color: var(--status-success);
}
.s-id     { font-weight:600; color:var(--text-secondary); }
.s-status { color:var(--text-secondary); }
.s-drug   { color:var(--text-main); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.s-qr     { flex-shrink:0; }
.s-update { font-size:0.72rem; color:var(--text-secondary); opacity:0.5; grid-column:1/-1; }

.empty-state   { flex:1; display:flex; align-items:center; justify-content:center; color:var(--text-secondary); }
.footer-update { font-size:0.75rem; color:var(--text-secondary); opacity:0.5; margin-top:var(--spacing-2); flex-shrink:0; }
</style>
