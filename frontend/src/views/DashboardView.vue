<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getHistory, getMeta, getServers, refreshServer, getAlerts, ApiError } from '../api'
import type { AlertRow, Meta, ServerSummary } from '../types'
import { pointsLabel, timeAgo } from '../format'
import TopBar from '../components/TopBar.vue'
import Icon from '../components/Icon.vue'
import ServerCard from '../components/ServerCard.vue'
import { toast } from '../toast'

const servers = ref<ServerSummary[]>([])
const meta = ref<Meta | null>(null)
const activeAlerts = ref<AlertRow[]>([])
const todayMap = ref<Record<number, number | null>>({})
const loading = ref(true)
const refreshing = ref<number | null>(null)
let timer: ReturnType<typeof setInterval> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
let pollLeft = 0

/** 操作后轮询列表（5s×6）捕捉延迟状态迁移（stop/restore 生效有滞后，规格 §12）。 */
function startPolling() {
  if (pollTimer) { pollLeft = 6; return }
  pollLeft = 6
  pollTimer = setInterval(async () => {
    pollLeft -= 1
    try {
      servers.value = await getServers()
    } catch { /* 轮询失败容忍，等下一轮 */ }
    if (pollLeft <= 0) {
      if (pollTimer) clearInterval(pollTimer)
      pollTimer = null
    }
  }, 5000)
}

function onOpDone(updated: ServerSummary | null) {
  if (updated) {
    const i = servers.value.findIndex((x) => x.id === updated.id)
    if (i >= 0) servers.value[i] = updated
  }
  startPolling()
}

async function load() {
  try {
    const [list, active] = await Promise.all([
      getServers(),
      getAlerts(true).catch(() => null),   // 横幅数据失败容忍
    ])
    servers.value = list
    if (active) activeAlerts.value = active
    const hist = await Promise.all(
      list.map((s) => getHistory(s.id, '24h').catch(() => null)),
    )
    const map: Record<number, number | null> = {}
    list.forEach((s, i) => {
      const du = hist[i]?.daily_usage ?? []
      map[s.id] = du.length ? du[du.length - 1].bytes : null
    })
    todayMap.value = map
    meta.value = await getMeta().catch(() => null)
  } catch (e) {
    if (e instanceof ApiError && e.code === 'unauthorized') return
    toast('数据加载失败，稍后自动重试', 'warn')
  } finally {
    loading.value = false
  }
}

async function refresh(id: number) {
  if (refreshing.value !== null) return
  refreshing.value = id
  try {
    const updated = await refreshServer(id)
    const i = servers.value.findIndex((s) => s.id === id)
    if (i >= 0) servers.value[i] = updated
    toast(`已刷新 ${updated.name}`)
    // 顺带更新该机今日用量（失败容忍）
    getHistory(id, '24h')
      .then((h) => {
        const du = h.daily_usage
        todayMap.value = { ...todayMap.value, [id]: du.length ? du[du.length - 1].bytes : null }
      })
      .catch(() => {})
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.code === 'refresh_ttl') toast('刚刷新过，请 1 分钟后再试', 'warn')
      else toast(e.message, 'danger')
    } else {
      toast('网络错误', 'danger')
    }
  } finally {
    refreshing.value = null
  }
}

const DANGER_TYPES = ['offline', 'traffic_critical', 'collect_error']
const banner = computed(() => {
  if (!activeAlerts.value.length) return null
  const lv = activeAlerts.value.some((a) => DANGER_TYPES.includes(a.type)) ? 'danger' : 'warn'
  return { level: lv, text: `${activeAlerts.value.length} 条未解决告警 — 点击查看` }
})

const footerText = computed(() => {
  const parts: string[] = []
  parts.push(meta.value ? pointsLabel(meta.value.rate_limit) : '点数未知')
  parts.push(meta.value ? timeAgo(meta.value.last_sample_at) : '尚未采样')
  if (meta.value?.mock) parts.push('演示模式')
  return parts.join(' · ')
})

onMounted(() => {
  load()
  timer = setInterval(load, 60_000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="page grid-bg">
    <TopBar />
    <router-link v-if="banner" class="banner" :data-level="banner.level" to="/alerts">
      <Icon name="alert" :size="15" /> {{ banner.text }}
    </router-link>
    <main>
      <p v-if="loading" class="loading">载入中…</p>
      <p v-else-if="servers.length === 0" class="empty">还没有服务器 —— 用 mock 模式或通过 API 添加</p>
      <section class="cards">
        <ServerCard
          v-for="(s, i) in servers" :key="s.id"
          :class="['rise', i === 0 ? 'rise-1' : 'rise-2']"
          :server="s" :today-bytes="todayMap[s.id] ?? null"
          :refreshing="refreshing === s.id"
          @refresh="refresh(s.id)"
          @opdone="onOpDone"
        />
      </section>
    </main>
    <footer class="foot num">{{ footerText }}</footer>
  </div>
</template>

<style scoped>
.page { min-height: 100vh; display: flex; flex-direction: column; }
main { flex: 1; width: min(1020px, 100% - 32px); margin: 24px auto 0; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(390px, 100%), 1fr)); gap: 18px; }
.loading, .empty { color: var(--ink-2); text-align: center; padding: 60px 0; font-size: 14px; }
.foot { text-align: center; color: var(--ink-3); font-size: 11.5px; padding: 20px 0 22px; }
.banner {
  width: min(1020px, 100% - 32px); margin: 14px auto 0;
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; border-radius: var(--radius-lg);
  font-size: 13px; font-weight: 550; text-decoration: none;
}
.banner[data-level='danger'] { background: var(--danger-bg); color: var(--danger); }
.banner[data-level='warn'] { background: var(--warn-bg); color: var(--warn); border: 1px solid var(--warn-border); }
</style>
