<template>
  <div class="layout">
    <nav class="sidebar">
      <div class="sidebar-brand">
        <span class="brand-dot"></span>
        <span class="brand-text">配药系统</span>
      </div>
      <router-link
        v-for="r in navRoutes" :key="r.path" :to="r.path"
        class="nav-item" active-class="nav-item--active"
      >
        <el-icon class="nav-icon" v-if="r.meta?.icon">
          <component :is="Icons[r.meta.icon as keyof typeof Icons]" />
        </el-icon>
        <span class="nav-label">{{ r.meta?.label }}</span>
      </router-link>
      <div class="sidebar-status">
        <span class="status-dot" :class="voiceStore.isConnected ? 'status-dot--ok' : 'status-dot--off'"></span>
        <span class="status-text">{{ voiceStore.isConnected ? '已连接' : '未连接' }}</span>
      </div>
    </nav>
    <main class="content"><router-view /></main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useVoiceStore } from '@/stores/voice'
import * as Icons from '@element-plus/icons-vue'
const voiceStore = useVoiceStore()
const router = useRouter()
const navRoutes = computed(() => router.getRoutes().filter((r) => r.meta?.label))
onMounted(() => { voiceStore.connect() })
</script>

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body, #app { height: 100%; overflow: hidden; }
</style>

<style scoped>
.layout { display: flex; height: 100vh; overflow: hidden; }
.sidebar { width: 200px; flex-shrink: 0; background: var(--wf-black); display: flex; flex-direction: column; padding: 16px 0; overflow-y: auto; }
.sidebar-brand { display: flex; align-items: center; gap: 10px; padding: 0 20px 20px; border-bottom: 1px solid var(--wf-gray-800); }
.brand-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--wf-blue); flex-shrink: 0; }
.brand-text { font-size: 14px; font-weight: 600; color: var(--wf-white); letter-spacing: 0.4px; text-transform: uppercase; }
.nav-item { display: flex; align-items: center; gap: 10px; padding: 14px 20px; text-decoration: none; color: var(--wf-text-muted); font-size: 14px; font-weight: 500; transition: background 0.15s, color 0.15s; }
.nav-item:hover { background: var(--wf-gray-800); color: var(--wf-white); }
.nav-item--active { background: var(--wf-gray-800); color: var(--wf-white); border-left: 2px solid var(--wf-blue); }
.nav-icon { font-size: 16px; width: 20px; text-align: center; }
.sidebar-status { margin-top: auto; padding: 16px 20px; display: flex; align-items: center; gap: 8px; border-top: 1px solid var(--wf-gray-800); }
.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.status-dot--ok  { background: var(--wf-green); }
.status-dot--off { background: var(--wf-gray-mid); }
.status-text { font-size: 12px; color: var(--wf-text-muted); font-weight: 500; }
.content { flex: 1; overflow: hidden; display: flex; flex-direction: column; background: var(--wf-bg-page); }
</style>
