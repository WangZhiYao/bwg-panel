<script setup lang="ts">
import { toasts } from './toast'
</script>

<template>
  <router-view />
  <div class="toasts" aria-live="polite">
    <div v-for="t in toasts" :key="t.id" class="toast" :data-kind="t.kind">{{ t.text }}</div>
  </div>
</template>

<style scoped>
.toasts {
  position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
  display: flex; flex-direction: column; gap: 8px; z-index: 99; align-items: center;
}
.toast {
  background: var(--dark); color: var(--dark-ink); padding: 9px 16px;
  border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); font-size: 13px;
  animation: rise 0.25s ease both;
}
.toast[data-kind='warn'] { background: var(--warn); }
.toast[data-kind='danger'] { background: var(--danger); }
</style>
