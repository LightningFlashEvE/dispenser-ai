<template>
  <div class="app-container">
    <NavSidebar />
    <main class="main-content">
      <slot></slot>
    </main>
  </div>
</template>

<script setup lang="ts">
import NavSidebar from './NavSidebar.vue';
</script>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background-color: var(--bg-page);
}

.main-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-5);
  display: flex;
  flex-direction: column;
}
</style>
