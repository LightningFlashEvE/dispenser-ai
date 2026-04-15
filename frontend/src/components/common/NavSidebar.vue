<template>
  <aside class="sidebar">
    <div class="logo">Dispenser AI</div>
    <nav class="nav-links">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        active-class="active"
      >
        {{ item.name }}
      </router-link>
    </nav>
  </aside>
</template>

<script setup lang="ts">
const navItems = [
  { name: '系统状态', path: '/status' },
  { name: '手动控制', path: '/manual' },
  { name: '库存管理', path: '/inventory' },
  { name: '配方库',   path: '/formulas' },
  { name: '操作日志', path: '/logs' },
  { name: '工位识别', path: '/vision' },
  { name: '系统设置', path: '/settings' },
]
</script>

<style scoped>
.sidebar {
  width: 220px;
  background-color: var(--bg-sidebar);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 var(--spacing-4);
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--text-main);
  border-bottom: 1px solid var(--border-color);
}

.nav-links {
  display: flex;
  flex-direction: column;
  padding: var(--spacing-4) 0;
  gap: var(--spacing-1);
}

.nav-item {
  text-decoration: none;
  color: var(--text-secondary);
  padding: var(--spacing-3) var(--spacing-4);
  font-size: 0.95rem;
  transition: color 0.2s, background-color 0.2s;
  border-left: 3px solid transparent;
}

.nav-item:hover {
  background-color: var(--bg-card-hover);
  color: var(--text-main);
}

.nav-item.active {
  background-color: var(--bg-card);
  color: var(--primary-blue);
  border-left-color: var(--primary-blue);
}
</style>
