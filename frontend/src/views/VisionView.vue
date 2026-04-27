<template>
  <div class="page placeholder-page">
    <div class="placeholder-icon">📷</div>
    <h2 class="placeholder-title">视觉识别</h2>
    <p class="placeholder-text">工位有无检测 · 二维码识别结果将在此展示</p>
    <p class="placeholder-sub">（功能开发中，后端就绪后接入 WebSocket vision_result 消息）</p>
  </div>
</template>
<style scoped>
.page { display: flex; flex-direction: column; height: 100%; }
.placeholder-page { align-items: center; justify-content: center; gap: 12px; color: #ababab; }
.placeholder-icon { font-size: 56px; }
.placeholder-title { font-size: 22px; font-weight: 600; color: #363636; }
.placeholder-text { font-size: 15px; }
.placeholder-sub { font-size: 13px; color: #d8d8d8; }
</style>
