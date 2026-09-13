<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PowerAction, ServerSummary } from '../types'
import { daysUntil, humanBytes, pct, statusLabel } from '../format'
import TrafficRing from './TrafficRing.vue'
import ResourceBar from './ResourceBar.vue'
import Icon from './Icon.vue'
import ConfirmDialog from './ConfirmDialog.vue'
import SnapshotMenu from './SnapshotMenu.vue'
import { ApiError, powerServer } from '../api'
import { toast } from '../toast'

const props = defineProps<{ server: ServerSummary; todayBytes: number | null; refreshing?: boolean }>()
const emit = defineEmits<{ refresh: []; opdone: [server: ServerSummary | null] }>()

const s = computed(() => props.server)
const latest = computed(() => s.value.latest)
const statusOk = computed(() => latest.value?.status === 'running')
const memUsedKb = computed(() =>
  latest.value && latest.value.mem_total_kb !== null && latest.value.mem_available_kb !== null
    ? latest.value.mem_total_kb - latest.value.mem_available_kb : null,
)
const diskUsedB = computed(() => {
  const u = latest.value?.disk_used_b
  return u !== null && u !== undefined ? u : null
})
const diskTotalB = computed(() => latest.value?.disk_quota_b ?? null)
const ipText = computed(() => s.value.ip_addresses[0] ?? '无 IPv4')
const trafficPct = computed(() => pct(s.value.traffic.used, s.value.traffic.quota))

async function copyIp() {
  if (ipText.value === '无 IPv4') return
  try {
    await navigator.clipboard.writeText(ipText.value)
    toast(`已复制 ${ipText.value}`)
  } catch {
    toast('复制失败（需 HTTPS 或 localhost）', 'warn')
  }
}

const opBusy = ref<PowerAction | null>(null)
const snapshotOpen = ref(false)

interface PowerAsk {
  action: PowerAction
  title: string
  message: string
  danger?: boolean
  strong?: boolean
  secondaryText?: string
}
const powerAsk = ref<PowerAsk | null>(null)

function askRestart() {
  powerAsk.value = {
    action: 'restart', title: '重启服务器',
    message: `确定重启「${s.value.name}」？重启期间服务会短暂中断。`,
  }
}

function askPower() {
  if (statusOk.value) {
    powerAsk.value = {
      action: 'stop', title: '关机服务器',
      message: `确定关机「${s.value.name}」？`, danger: true,
      secondaryText: '强制断电…',
    }
  } else {
    powerAsk.value = {
      action: 'start', title: '开机服务器',
      message: `「${s.value.name}」当前未运行，确定开机？`,
    }
  }
}

function askKill() {
  powerAsk.value = {
    action: 'kill', title: '强制断电', danger: true, strong: true,
    message: `强制断电相当于直接拔电源，可能损坏数据。`,
  }
}

const POWER_TOAST: Record<PowerAction, string> = {
  start: '开机指令已执行', stop: '关机指令已执行',
  restart: '重启指令已执行', kill: '强制断电指令已执行',
}

async function runPower(action: PowerAction, confirmName?: string) {
  if (opBusy.value) return
  opBusy.value = action
  powerAsk.value = null
  try {
    const updated = await powerServer(s.value.id, action, confirmName)
    toast(POWER_TOAST[action])
    emit('opdone', updated)
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '网络错误', 'danger')
  } finally {
    opBusy.value = null
  }
}
</script>

<template>
  <article class="card" :class="{ warnring: (trafficPct ?? 0) >= 80 }">
    <header>
      <div>
        <h2>{{ s.name }}</h2>
        <p class="meta">{{ s.node_location ?? '未知机房' }} · {{ s.os ?? '?' }} · {{ (s.vm_type ?? '?').toUpperCase() }}</p>
      </div>
      <span class="badge" :class="statusOk ? 'ok' : 'down'">
        <i class="dot" :class="{ 'dot-live': statusOk }" />{{ statusLabel(latest?.status) }}
      </span>
    </header>

    <div
      class="ip num" title="点击复制（回车）" role="button" tabindex="0"
      @click="copyIp" @keydown.enter.prevent="copyIp"
    >{{ ipText }} <Icon name="copy" :size="13" class="copy" /></div>

    <div class="traffic">
      <TrafficRing :used="s.traffic.used" :quota="s.traffic.quota" />
      <div class="facts">
        <div>月流量 <b class="num">{{ humanBytes(s.traffic.used) }}</b><span class="dim num"> / {{ s.traffic.quota > 0 ? humanBytes(s.traffic.quota) : '未知' }}</span></div>
        <div>{{ daysUntil(s.traffic.next_reset) || '重置时间未知' }}</div>
        <div>今日已用 <b class="num">{{ todayBytes === null ? '--' : humanBytes(todayBytes) }}</b></div>
      </div>
    </div>

    <div class="bars">
      <ResourceBar label="磁盘" :used="diskUsedB" :total="diskTotalB" />
      <ResourceBar label="内存" :used="memUsedKb" :total="latest?.mem_total_kb ?? null" />
      <div class="load">
        负载 <b class="num">{{ latest?.load_average ?? '--' }}</b>
        <template v-if="latest?.cpu_throttled">
          <span class="throttle"><Icon name="alert" :size="12" /> CPU 节流</span>
        </template>
      </div>
    </div>

    <footer>
      <button class="ghost" :disabled="opBusy !== null" @click="askRestart">
        <Icon name="restart" :size="14" />重启
      </button>
      <button class="ghost" :disabled="opBusy !== null" @click="askPower">
        <Icon name="power" :size="14" />{{ statusOk ? '关机' : '开机' }}
      </button>
      <button class="ghost" :class="{ active: snapshotOpen }" :disabled="opBusy !== null" @click="snapshotOpen = !snapshotOpen">
        <Icon name="camera" :size="14" />快照 <Icon name="chevron-down" :size="14" class="chev" />
      </button>
      <button class="solid" :disabled="props.refreshing" @click="$emit('refresh')">
        <Icon name="refresh" :size="14" />{{ props.refreshing ? '刷新中…' : '刷新' }}
      </button>

      <ConfirmDialog
        v-if="powerAsk"
        :title="powerAsk.title" :message="powerAsk.message"
        :danger="powerAsk.danger"
        :confirm-text="powerAsk.action === 'kill' ? '强制断电' : '确认'"
        :strong="powerAsk.strong ? { label: `输入昵称「${s.name}」确认`, expected: s.name } : null"
        :secondary-text="powerAsk.secondaryText || ''"
        :busy="opBusy !== null"
        @confirm="(typed: string) => runPower(powerAsk!.action, powerAsk!.strong ? typed : undefined)"
        @cancel="powerAsk = null"
        @secondary="askKill"
      />
      <SnapshotMenu
        v-if="snapshotOpen"
        :server="s"
        @close="snapshotOpen = false"
        @changed="emit('opdone', null)"
      />
    </footer>

    <span v-if="s.stale" class="stale" title="超过 15 分钟无新采样"><Icon name="alert" :size="12" /> 数据可能过期</span>
  </article>
</template>

<style scoped>
.card {
  position: relative; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-xl); box-shadow: var(--shadow-md); padding: 20px;
  display: flex; flex-direction: column; gap: 14px;
  transition: border-color 0.15s ease;
}
.card:hover { border-color: var(--border-strong); }
.card.warnring { border-color: var(--warn-strong); box-shadow: var(--shadow-md), 0 0 0 1px var(--warn-border) inset; }
header { display: flex; justify-content: space-between; align-items: flex-start; }
h2 { margin: 0; font-size: 16px; font-weight: 650; letter-spacing: -0.01em; }
.meta { margin: 4px 0 0; font-size: 12.5px; color: var(--ink-3); }
.badge { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; padding: 3px 10px; border-radius: 99px; flex: none; }
.badge.ok { background: var(--ok-bg); color: var(--ok); }
.badge.down { background: var(--danger-bg); color: var(--danger); }
.dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.ip {
  font-size: 12.5px; color: var(--ink-2); cursor: pointer; width: fit-content;
  display: inline-flex; align-items: center; gap: 7px;
  padding: 5px 9px; margin: -6px 0 0 -9px; border-radius: var(--radius-sm);
  transition: background-color 0.15s ease, color 0.15s ease;
}
.ip:hover { background: var(--surface-2); color: var(--ink); }
.ip:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.ip:hover .copy { opacity: 0.8; }
.copy { opacity: 0.45; }
.traffic {
  display: flex; gap: 16px; align-items: center;
  padding: 14px 16px; background: var(--surface-2);
  border: 1px solid var(--track); border-radius: var(--radius-lg);
}
.facts { flex: 1; font-size: 12.5px; color: var(--ink-2); display: grid; gap: 5px; }
.facts b { font-size: 14px; color: var(--ink); }
.dim { color: var(--ink-3); }
.bars { display: grid; gap: 9px; }
.load { font-size: 12.5px; color: var(--ink-2); display: flex; align-items: center; gap: 8px; }
.throttle {
  color: var(--warn); font-weight: 600; font-size: 11.5px;
  display: inline-flex; align-items: center; gap: 4px;
  background: var(--warn-bg); border: 1px solid var(--warn-border);
  padding: 2px 8px; border-radius: 99px;
}
footer { display: flex; gap: 8px; margin-top: auto; padding-top: 14px; border-top: 1px solid var(--track); }
button {
  flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  padding: 8px 0; border-radius: var(--radius-md); font-size: 12.5px;
  border: 1px solid var(--border); background: var(--surface); color: var(--ink-2);
  transition: border-color 0.15s ease, color 0.15s ease, transform 0.06s;
}
button:not(:disabled):hover { border-color: var(--border-strong); color: var(--ink); }
button.solid { background: var(--dark); border-color: var(--dark); color: var(--dark-ink); font-weight: 550; }
button:not(:disabled):active { transform: scale(0.97); }
button:disabled { opacity: 0.45; cursor: not-allowed; }
button.ghost.active { border-color: var(--primary); color: var(--primary); }
button.ghost.active .chev { transform: rotate(180deg); }
.chev { transition: transform 0.15s ease; }
.stale {
  position: absolute; top: -9px; right: 16px; background: var(--warn-bg); color: var(--warn);
  font-size: 11px; padding: 2px 10px; border-radius: 99px; border: 1px solid var(--warn-border);
  display: inline-flex; align-items: center; gap: 4px;
}
</style>
