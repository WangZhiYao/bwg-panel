<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getAlerts, logout } from '../api'
import Icon from './Icon.vue'

const router = useRouter()
const activeCount = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

async function poll() {
  try {
    activeCount.value = (await getAlerts(true)).length
  } catch { /* 拉取失败保留旧值 */ }
}

async function doLogout() {
  try { await logout() } catch { /* 会话已失效也直接走 */ }
  router.replace('/login')
}

onMounted(() => {
  poll()
  timer = setInterval(poll, 60_000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<template>
  <header class="bar">
    <router-link class="brand" to="/">
      <span class="mark"><Icon name="server" /></span>
      BWG 面板
    </router-link>
    <span class="right">
      <router-link class="link" to="/trends"><Icon name="chart" :size="14" />趋势</router-link>
      <router-link class="link bell" to="/alerts" aria-label="告警">
        <Icon name="bell" :size="15" />
        <span v-if="activeCount > 0" class="badge num">{{ activeCount > 99 ? '99+' : activeCount }}</span>
      </router-link>
      <router-link class="link" to="/settings"><Icon name="settings" :size="14" />设置</router-link>
      <a
        class="link" role="button" tabindex="0"
        @click="doLogout" @keydown.enter.prevent="doLogout" @keydown.space.prevent="doLogout"
      ><Icon name="logout" :size="14" />退出</a>
    </span>
  </header>
</template>

<style scoped>
.bar {
  background: rgb(255 255 255 / 0.85); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
  color: var(--ink); min-height: 54px; padding: 8px 24px;
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  position: sticky; top: 0; z-index: 10;
  border-bottom: 1px solid var(--border);
}
.brand {
  display: inline-flex; align-items: center; gap: 10px;
  font-weight: 650; font-size: 15px; letter-spacing: -0.01em;
  color: var(--ink); text-decoration: none;
  padding: 4px 6px; margin: -4px -6px; border-radius: var(--radius-sm);
  transition: opacity 0.15s ease;
}
.brand:hover { opacity: 0.85; }
.brand:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.mark {
  width: 30px; height: 30px; border-radius: var(--radius-md); background: var(--primary-soft); color: var(--primary-deep);
  display: inline-flex; align-items: center; justify-content: center;
}
.right { margin-left: auto; display: flex; gap: 18px; }
.link {
  color: var(--ink-2); font-size: 13px; cursor: pointer;
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 6px; margin: -4px -6px; border-radius: var(--radius-sm);
  transition: color 0.15s ease, background-color 0.15s ease;
}
.link:hover { color: var(--primary); }
.link:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.bell { position: relative; }
.badge {
  position: absolute; top: -4px; right: -8px;
  min-width: 16px; height: 16px; padding: 0 4px;
  border-radius: 999px; background: var(--danger); color: var(--dark-ink);
  font-size: 10px; line-height: 16px; text-align: center;
}
</style>
