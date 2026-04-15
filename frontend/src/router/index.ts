import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/status',
  },
  {
    path: '/status',
    name: 'Status',
    component: () => import('@/views/VoiceView.vue'),
  },
  {
    path: '/manual',
    name: 'Manual',
    component: () => import('@/views/ManualView.vue'),
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
