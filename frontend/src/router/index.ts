import { createRouter, createWebHashHistory } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import VoiceView from '@/views/VoiceView.vue'
import InventoryView from '@/views/InventoryView.vue'
import WeightView from '@/views/WeightView.vue'
import FormulasView from '@/views/FormulasView.vue'
import LogsView from '@/views/LogsView.vue'
import VisionView from '@/views/VisionView.vue'
import SystemStatusView from '@/views/SystemStatusView.vue'
import SettingsView from '@/views/SettingsView.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/',          redirect: '/dashboard' },
    { path: '/dashboard', component: DashboardView, meta: { label: 'Dashboard', icon: 'LayoutDashboard', order: 1 } },
    { path: '/voice',     component: VoiceView,     meta: { label: '任务执行', icon: 'AudioWaveform', order: 2 } },
    { path: '/weight',    component: WeightView,    meta: { label: '实时称重', icon: 'Scale', order: 3 } },
    { path: '/inventory', component: InventoryView, meta: { label: '药品库存', icon: 'Boxes', order: 4 } },
    { path: '/formulas',  component: FormulasView,  meta: { label: '配方管理', icon: 'ClipboardList', order: 5 } },
    { path: '/logs',      component: LogsView,      meta: { label: '日志报警', icon: 'ScrollText', order: 6 } },
    { path: '/vision',    component: VisionView,    meta: { label: '视觉识别', icon: 'Camera', order: 7 } },
    { path: '/settings',  component: SettingsView,  meta: { label: '系统设置', icon: 'Settings', order: 8 } },
    { path: '/status',    component: SystemStatusView, meta: { label: '系统状态', icon: 'Gauge', nav: false } },
  ],
})
