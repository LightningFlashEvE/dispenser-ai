<template>
  <div class="voice-view">
    <div class="status-bar" :class="dialogState.toLowerCase()">
      <div class="status-indicator"></div>
      <span class="status-text">{{ statusText }}</span>
    </div>

    <div class="main-grid">
      <div class="interaction-col">
        <div class="interaction-card">
          <div v-if="latestQuestion" class="ai-question">
            {{ latestQuestion }}
          </div>
          
          <div class="caption-box">
            <div v-if="realtimeCaption" class="caption-text realtime">
              {{ realtimeCaption }}
            </div>
            <div v-else class="caption-text placeholder">
              等待语音输入...
            </div>
          </div>
        </div>

        <div class="balance-card">
          <div class="balance-title">天平读数</div>
          <div class="balance-reading" :class="{ stable: isBalanceStable }">
            <span class="value">{{ balanceValue }}</span>
            <span class="unit">mg</span>
          </div>
        </div>
      </div>

      <div class="history-col">
        <h3 class="history-title">对话历史</h3>
        <div class="history-list">
          <div 
            v-for="(msg, index) in transcript" 
            :key="index"
            class="message"
            :class="msg.role"
          >
            <div class="msg-time">{{ msg.timestamp }}</div>
            <div class="msg-text">{{ msg.text }}</div>
          </div>
          <div v-if="transcript.length === 0" class="empty-history">
            暂无对话历史
          </div>
        </div>
      </div>
    </div>

    <div class="action-bar">
      <el-button class="cancel-btn" plain @click="handleCancel">取消</el-button>
      <button
        class="mic-btn"
        :class="{ active: dialogState === 'LISTENING' }"
        @click="handleMicToggle"
      >
        <el-icon :size="32"><Microphone /></el-icon>
      </button>
      <div class="connection-status" :class="{ connected: isConnected }">
        {{ isConnected ? '系统已连接' : '系统未连接' }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useVoiceStore } from '@/stores/voice';
import { useVisionStore } from '@/stores/vision';
import { sendJson } from '@/services/websocket';

const voiceStore = useVoiceStore();
const visionStore = useVisionStore();

const { 
  dialogState, 
  realtimeCaption, 
  transcript, 
  latestQuestion, 
  isConnected 
} = storeToRefs(voiceStore);

const { balanceReading } = storeToRefs(visionStore);

const statusText = computed(() => {
  const map: Record<string, string> = {
    'IDLE': '空闲中',
    'LISTENING': '正在聆听...',
    'PROCESSING': '处理中...',
    'ASKING': '需补充信息',
    'EXECUTING': '正在执行...',
    'FEEDBACK': '执行完成',
    'ERROR': '发生错误'
  };
  return map[dialogState.value] || '未知状态';
});

const balanceValue = computed(() => {
  if (!balanceReading.value) return '0.0';
  return balanceReading.value.mass_mg.toFixed(1);
});

const isBalanceStable = computed(() => {
  return balanceReading.value?.stable ?? false;
});

function handleCancel() {
  sendJson({ type: 'cancel' });
}

function handleMicToggle() {
  if (dialogState.value === 'LISTENING') {
    voiceStore.setState('IDLE');
  } else {
    voiceStore.setState('LISTENING');
  }
}
</script>

<style scoped>
.voice-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: var(--spacing-4);
}

.status-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  background-color: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}

.status-indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background-color: var(--status-idle);
}

.status-bar.idle .status-indicator { background-color: var(--status-idle); }
.status-bar.listening .status-indicator { 
  background-color: var(--status-success); 
  animation: pulse 1.5s infinite;
}
.status-bar.processing .status-indicator { background-color: var(--primary-blue); }
.status-bar.asking .status-indicator { background-color: var(--status-warning); }
.status-bar.executing .status-indicator { background-color: var(--primary-blue); }
.status-bar.feedback .status-indicator { background-color: var(--status-success); }
.status-bar.error .status-indicator { background-color: var(--status-error); }

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(0, 215, 34, 0.4); }
  70% { box-shadow: 0 0 0 10px rgba(0, 215, 34, 0); }
  100% { box-shadow: 0 0 0 0 rgba(0, 215, 34, 0); }
}

.main-grid {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: var(--spacing-4);
  flex: 1;
  min-height: 0;
}

.interaction-col {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.interaction-card {
  flex: 1;
  background-color: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  padding: var(--spacing-5);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.ai-question {
  background-color: rgba(255, 107, 0, 0.1);
  border: 1px solid var(--status-warning);
  color: var(--status-warning);
  padding: var(--spacing-4);
  border-radius: var(--radius-sm);
  font-size: 1.1rem;
  font-weight: 500;
}

.caption-box {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  text-align: center;
}

.caption-text.placeholder {
  color: var(--text-secondary);
  opacity: 0.5;
}

.balance-card {
  height: 120px;
  background-color: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  padding: var(--spacing-4);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.balance-title {
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.balance-reading {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-2);
  color: var(--text-secondary);
}

.balance-reading.stable {
  color: var(--status-success);
}

.balance-reading .value {
  font-size: 3rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.history-col {
  background-color: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
}

.history-title {
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-color);
  color: var(--text-main);
}

.history-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-4);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.message {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.msg-time {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.msg-text {
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-sm);
  background-color: var(--bg-card-hover);
  width: fit-content;
  max-width: 90%;
}

.message.user {
  align-items: flex-end;
}
.message.user .msg-text {
  background-color: rgba(20, 110, 245, 0.1);
  color: var(--primary-blue);
  border: 1px solid rgba(20, 110, 245, 0.2);
}

.empty-history {
  color: var(--text-secondary);
  text-align: center;
  margin-top: var(--spacing-5);
}

.action-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  padding: var(--spacing-4) 0;
}

.cancel-btn {
  position: absolute;
  left: 0;
  background: transparent;
  color: var(--text-secondary);
  border-color: var(--border-color);
}

.connection-status {
  position: absolute;
  right: 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
}
.connection-status.connected {
  color: var(--status-success);
}

.mic-btn {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  border: none;
  background-color: var(--bg-card);
  box-shadow: var(--shadow-main);
  border: 1px solid var(--border-color);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.mic-btn .el-icon {
  color: var(--text-main);
}

.mic-btn.active {
  background-color: var(--status-error);
  transform: scale(1.05);
}

.mic-btn:hover:not(.active) {
  background-color: var(--bg-card-hover);
}
</style>
