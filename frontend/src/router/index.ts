import { createRouter, createWebHashHistory } from 'vue-router'
import VoiceView from '@/views/VoiceView.vue'
import InventoryView from '@/views/InventoryView.vue'
import FormulasView from '@/views/FormulasView.vue'
import LogsView from '@/views/LogsView.vue'
import VisionView from '@/views/VisionView.vue'
import SystemStatusView from '@/views/SystemStatusView.vue'
import SettingsView from '@/views/SettingsView.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/',          redirect: '/voice' },
    { path: '/voice',     component: VoiceView,     meta: { label: '语音交互', icon: 'Microphone' } },
    { path: '/inventory', component: InventoryView, meta: { label: '药品库存', icon: 'Box' } },
    { path: '/formulas',  component: FormulasView,  meta: { label: '配方管理', icon: 'Document' } },
    { path: '/logs',      component: LogsView,      meta: { label: '操作日志', icon: 'List' } },
    { path: '/vision',    component: VisionView,    meta: { label: '视觉识别', icon: 'Camera' } },
    { path: '/status',    component: SystemStatusView, meta: { label: '系统状态', icon: 'Odometer' } },
    { path: '/settings',  component: SettingsView,  meta: { label: '系统设置', icon: 'Setting' } },
  ],
})
