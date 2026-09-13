<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ackAlert, getAlerts } from '../api'
import type { AlertRow } from '../types'
import { alertTypeLabel, formatTs } from '../format'
import { toast } from '../toast'
import TopBar from '../components/TopBar.vue'
import Icon from '../components/Icon.vue'

const alerts = ref<AlertRow[]>([])
const loading = ref(true)
const failed = ref(false)
const refreshing = ref(false)
const acking = ref<number | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

async function load() {
  try {
    alerts.value = await getAlerts()
    failed.value = false
  } catch {
    failed.value = true // 有旧数据则继续展示旧数据，等下一轮
  } finally {
    loading.value = false
  }
}

async function refresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    alerts.value = await getAlerts()
    failed.value = false
  } catch {
    toast('刷新失败，请稍后重试', 'warn')
  } finally {
    refreshing.value = false
  }
}

const active = computed(() => alerts.value.filter((a) => !a.resolved_at))
const history = computed(() => alerts.value.filter((a) => a.resolved_at))

function level(t: string): 'danger' | 'warn' {
  return ['offline', 'traffic_critical', 'collect_error'].includes(t) ? 'danger' : 'warn'
}

async function ack(a: AlertRow) {
  if (acking.value !== null) return
  acking.value = a.id
  try {
    await ackAlert(a.id)
    a.acknowledged = true   // 灰化保留；铃铛/横幅的口径在后端已剔除已确认项
  } catch {
    toast('操作失败，请重试', 'warn')
  } finally {
    acking.value = null
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 60_000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<template>
  <div class="page grid-bg">
    <TopBar />
    <main>
      <div class="head">
        <h1>告警</h1>
        <button class="btn" :disabled="refreshing" @click="refresh">
          <Icon name="refresh" :size="13" />{{ refreshing ? '刷新中…' : '刷新' }}
        </button>
      </div>
      <p v-if="loading" class="tip">载入中…</p>
      <p v-else-if="!alerts.length && failed" class="tip">加载失败 —— 60 秒后自动重试，或点右上角「刷新」</p>
      <p v-else-if="!alerts.length" class="tip">暂无告警 —— 一切正常</p>
      <template v-else>
        <section v-if="active.length">
          <h2>未解决（{{ active.length }}）</h2>
          <ul class="list">
            <li v-for="a in active" :key="a.id" class="row" :class="{ acked: a.acknowledged }" :data-level="level(a.type)">
              <span class="tag" :data-level="level(a.type)">{{ alertTypeLabel(a.type) }}</span>
              <div class="body">
                <p class="msg">{{ a.message }}</p>
                <p class="meta num">{{ a.server_name }} · {{ formatTs(a.triggered_at) }} · {{ a.notified ? '已推送' : '未推送' }}</p>
              </div>
              <span v-if="a.acknowledged" class="tag acked-tag">已确认</span>
              <button v-else class="btn ack" :disabled="acking === a.id" @click="ack(a)">知道了</button>
            </li>
          </ul>
        </section>
        <section v-if="history.length">
          <h2>历史</h2>
          <ul class="list dim">
            <li v-for="a in history" :key="a.id" class="row resolved">
              <span class="tag">{{ alertTypeLabel(a.type) }}</span>
              <div class="body">
                <p class="msg">{{ a.message }}</p>
                <p class="meta num">{{ a.server_name }} · {{ formatTs(a.triggered_at) }} → {{ formatTs(a.resolved_at) }} · {{ a.notified ? '已推送' : '未推送' }}</p>
              </div>
            </li>
          </ul>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.page { min-height: 100vh; display: flex; flex-direction: column; }
main { flex: 1; width: min(760px, 100% - 32px); margin: 24px auto 40px; }
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
h1 { font-size: 18px; font-weight: 650; margin: 4px 0 16px; }
.head h1 { margin-bottom: 0; }
h2 { font-size: 13px; font-weight: 600; color: var(--ink-2); margin: 18px 0 10px; }
.btn {
  padding: 7px 13px; border-radius: var(--radius-md); font-size: 12.5px;
  border: 1px solid var(--border); background: var(--surface); color: var(--ink-2);
  display: inline-flex; align-items: center; gap: 6px;
  transition: border-color 0.15s, color 0.15s;
}
.btn:not(:disabled):hover { border-color: var(--border-strong); color: var(--ink); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.tip { color: var(--ink-2); text-align: center; padding: 60px 0; font-size: 14px; }
.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.row {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
  padding: 12px 14px; display: flex; gap: 12px; align-items: flex-start;
  box-shadow: var(--shadow-xs);
}
.row[data-level='danger'] { border-left: 3px solid var(--danger); }
.row[data-level='warn'] { border-left: 3px solid var(--warn-strong); }
.row.resolved { opacity: 0.72; }
.row.acked { opacity: 0.55; }
.tag {
  flex: none; font-size: 11.5px; padding: 3px 8px; border-radius: 999px;
  background: var(--track); color: var(--ink-2); white-space: nowrap; margin-top: 1px;
}
.tag[data-level='danger'] { background: var(--danger-bg); color: var(--danger); }
.tag[data-level='warn'] { background: var(--warn-bg); color: var(--warn); }
.acked-tag { margin-top: 1px; margin-left: auto; color: var(--ink-3); }
.btn.ack { margin-left: auto; flex: none; padding: 5px 11px; font-size: 12px; }
.body { min-width: 0; }
.msg { margin: 0; font-size: 13.5px; color: var(--ink); line-height: 1.5; }
.meta { margin: 4px 0 0; font-size: 11.5px; color: var(--ink-3); }
.dim .row { border-left: 3px solid var(--border); }
</style>
