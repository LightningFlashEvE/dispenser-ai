<template>
  <transition name="slide-right">
    <div v-if="visible" class="session-panel">
      <div class="session-header">
        <span class="session-title">会话历史</span>
        <button class="btn-new" @click="onNewSession" title="新建会话">+ 新建</button>
        <button class="btn-close" @click="$emit('close')">×</button>
      </div>

      <div class="session-list">
        <div v-if="sessionsStore.isLoading" class="session-loading">加载中...</div>
        <div v-else-if="sessionsStore.sessions.length === 0" class="session-empty">
          暂无会话记录
        </div>
        <div
          v-for="s in sessionsStore.sessions"
          :key="s.session_id"
          class="session-item"
          :class="{ 'session-item--active': s.session_id === sessionsStore.currentSessionId }"
          @click="onSelectSession(s.session_id)"
        >
          <div class="session-item-main">
            <div class="session-item-title">{{ s.title || '新对话' }}</div>
            <div class="session-item-meta">
              <span>{{ formatDate(s.updated_at) }}</span>
              <span v-if="s.message_count">· {{ s.message_count }} 条消息</span>
            </div>
          </div>
          <button
            class="btn-delete"
            title="删除会话"
            @click.stop="onDeleteSession(s.session_id)"
          >🗑</button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { useSessionsStore } from '@/stores/sessions'

defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  close: []
  switch: [sessionId: string]
  new: []
}>()

const sessionsStore = useSessionsStore()

function formatDate(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const days = Math.floor(diff / 86400000)
  if (days === 0) return `今天 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (days === 1) return `昨天 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (days < 7) return `${days}天前`
  return `${d.getMonth() + 1}/${d.getDate()}`
}

async function onNewSession(): Promise<void> {
  emit('new')
}

async function onSelectSession(sessionId: string): Promise<void> {
  emit('switch', sessionId)
}

async function onDeleteSession(sessionId: string): Promise<void> {
  if (!confirm('确定删除该会话？')) return
  await sessionsStore.deleteSession(sessionId)
}
</script>

<style scoped>
.session-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 320px;
  height: 100vh;
  background: #fff;
  border-left: 1px solid #e8e8e8;
  box-shadow: -4px 0 16px rgba(0,0,0,0.08);
  display: flex;
  flex-direction: column;
  z-index: 100;
}
.session-header {
  display: flex;
  align-items: center;
  padding: 16px 16px;
  border-bottom: 1px solid #e8e8e8;
  gap: 8px;
}
.session-title {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  color: var(--wf-text-main);
}
.btn-new {
  background: #146ef5;
  color: #fff;
  border: none;
  border-radius: 4px;
  padding: 6px 12px;
  font-size: 13px;
  cursor: pointer;
  font-weight: 500;
}
.btn-new:hover { background: #0055d4; }
.btn-close {
  background: none;
  border: none;
  font-size: 20px;
  color: #888;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}
.btn-close:hover { color: #333; }
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}
.session-loading,
.session-empty {
  padding: 32px 16px;
  text-align: center;
  color: #aaa;
  font-size: 14px;
}
.session-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  gap: 8px;
  border-bottom: 1px solid #f5f5f5;
}
.session-item:hover { background: #f9f9f9; }
.session-item--active { background: #f0f6ff; }
.session-item--active:hover { background: #e8f0ff; }
.session-item-main { flex: 1; min-width: 0; }
.session-item-title {
  font-size: 14px;
  color: var(--wf-text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-item-meta {
  font-size: 12px;
  color: #aaa;
  margin-top: 2px;
}
.btn-delete {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  opacity: 0;
  padding: 4px;
  transition: opacity 0.15s;
}
.session-item:hover .btn-delete { opacity: 1; }
.btn-delete:hover { opacity: 0.6; }

/* transition */
.slide-right-enter-active, .slide-right-leave-active { transition: transform 0.25s ease; }
.slide-right-enter-from, .slide-right-leave-to { transform: translateX(100%); }
</style>
