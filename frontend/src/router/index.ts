import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/voice',
  },
  {
    path: '/voice',
    name: 'Voice',
    component: () => import('@/views/VoiceView.vue'),
  },
  {
    path: '/inventory',
    name: 'Inventory',
    component: () => import('@/views/InventoryView.vue'),
  },
  {
    path: '/formulas',
    name: 'Formulas',
    component: () => import('@/views/FormulasView.vue'),
  },
  {
    path: '/logs',
    name: 'Logs',
    component: () => import('@/views/LogsView.vue'),
  },
  {
    path: '/vision',
    name: 'Vision',
    component: () => import('@/views/VisionView.vue'),
  },
  {
    path: '/device',
    name: 'Device',
    component: () => import('@/views/DeviceView.vue'),
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/SettingsView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
