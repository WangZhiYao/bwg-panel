<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { getHistory, getServers } from '../api'
import type { HistoryRange, ServerSummary } from '../types'
import { humanBytes } from '../format'
import { CHART } from '../chart-theme'
import TopBar from '../components/TopBar.vue'
import Icon from '../components/Icon.vue'

const servers = ref<ServerSummary[]>([])
const selectedId = ref<number | null>(null)
const range = ref<HistoryRange>('7d')
const loading = ref(false)
const noData = ref(false)
const errorText = ref('')
let loadSeq = 0

let usageChart: echarts.ECharts | null = null
let resourceChart: echarts.ECharts | null = null

const RANGES: { key: HistoryRange; label: string }[] = [
  { key: '24h', label: '24 小时' },
  { key: '7d', label: '7 天' },
  { key: '30d', label: '30 天' },
]

async function initServers() {
  servers.value = await getServers()
  if (servers.value.length && selectedId.value === null) {
    selectedId.value = servers.value[0].id
  }
}

async function load() {
  if (selectedId.value === null) return
  const mySeq = ++loadSeq
  loading.value = true
  noData.value = false
  errorText.value = ''
  try {
    const { samples, daily_usage } = await getHistory(selectedId.value, range.value)
    if (mySeq !== loadSeq) return
    if (!samples.length && !daily_usage.length) noData.value = true

    usageChart?.setOption({
      title: { text: '流量消耗（按日）', left: 8, textStyle: { fontSize: 13, color: CHART.title } },
      tooltip: { valueFormatter: (v: unknown) => humanBytes(Number(v)) },
      grid: { left: 64, right: 16, top: 40, bottom: 28 },
      xAxis: { type: 'category', data: daily_usage.map((d) => d.date), axisLabel: { color: CHART.axis, fontSize: 11 } },
      yAxis: {
        type: 'value',
        axisLabel: { color: CHART.axis, fontSize: 11, formatter: (v: unknown) => humanBytes(Number(v)) },
        splitLine: { lineStyle: { color: CHART.grid } },
      },
      series: [{
        type: 'bar', data: daily_usage.map((d) => d.bytes),
        itemStyle: { color: CHART.primary, borderRadius: [4, 4, 0, 0] }, barMaxWidth: 28,
      }],
    })

    const memPct = samples
      .filter((s) => s.mem_total_kb && s.mem_available_kb !== null)
      .map((s) => [s.ts, Math.round(((s.mem_total_kb! - s.mem_available_kb!) / s.mem_total_kb!) * 100)])
    const diskPct = samples
      .filter((s) => s.disk_quota_b && s.disk_used_b !== null)
      .map((s) => [s.ts, Math.round((s.disk_used_b! / s.disk_quota_b!) * 100)])
    resourceChart?.setOption({
      title: { text: '内存 / 磁盘占用 %', left: 8, textStyle: { fontSize: 13, color: CHART.title } },
      tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => `${Number(v)}%` },
      legend: { right: 8, top: 6, textStyle: { fontSize: 11, color: CHART.axis } },
      grid: { left: 40, right: 16, top: 40, bottom: 28 },
      xAxis: { type: 'time', axisLabel: { color: CHART.axis, fontSize: 11 } },
      yAxis: {
        type: 'value', min: 0, max: 100,
        axisLabel: { color: CHART.axis, fontSize: 11, formatter: '{value}%' },
        splitLine: { lineStyle: { color: CHART.grid } },
      },
      series: [
        { name: '内存', type: 'line', showSymbol: false, data: memPct, lineStyle: { width: 2 }, itemStyle: { color: CHART.primary }, areaStyle: { opacity: 0.08 } },
        { name: '磁盘', type: 'line', showSymbol: false, data: diskPct, lineStyle: { width: 2 }, itemStyle: { color: CHART.secondary } },
      ],
    })
  } catch {
    if (mySeq === loadSeq) errorText.value = '数据加载失败，请稍后重试'
  } finally {
    if (mySeq === loadSeq) loading.value = false
  }
}

function onResize() {
  usageChart?.resize()
  resourceChart?.resize()
}

onMounted(async () => {
  usageChart = echarts.init(document.getElementById('usage-chart')!)
  resourceChart = echarts.init(document.getElementById('resource-chart')!)
  window.addEventListener('resize', onResize)
  try {
    await initServers()
    if (!servers.value.length) errorText.value = '暂无服务器'
  } catch {
    errorText.value = '服务器列表加载失败，请稍后刷新'
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  usageChart?.dispose()
  resourceChart?.dispose()
})

watch([selectedId, range], load)
</script>

<template>
  <div class="page grid-bg">
    <TopBar />
    <main>
      <div class="controls">
        <label class="selwrap">
          <select v-model="selectedId" class="sel">
            <option v-for="s in servers" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
          <Icon name="chevron-down" :size="14" class="selchev" />
        </label>
        <div class="ranges">
          <button
            v-for="r in RANGES" :key="r.key" :class="{ on: range === r.key }"
            @click="range = r.key"
          >{{ r.label }}</button>
        </div>
        <a
          class="back" role="button" tabindex="0"
          @click="$router.push('/')" @keydown.enter.prevent="$router.push('/')"
        >← 返回总览</a>
      </div>
      <p v-if="loading" class="hint">载入中…</p>
      <p v-else-if="noData" class="hint">该时间范围内暂无采样数据</p>
      <p v-else-if="errorText" class="hint">{{ errorText }}</p>
      <div id="usage-chart" class="chart" />
      <div id="resource-chart" class="chart" />
    </main>
  </div>
</template>

<style scoped>
.page { min-height: 100vh; display: flex; flex-direction: column; }
main { flex: 1; width: min(1020px, 100% - 32px); margin: 24px auto 0; }
.controls { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.selwrap { position: relative; display: inline-flex; }
.sel {
  appearance: none; padding: 8px 34px 8px 12px;
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface); font-size: 13px; color: var(--ink); cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.sel:focus { outline: none; border-color: var(--primary); box-shadow: var(--focus-ring); }
.selchev { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); color: var(--ink-3); pointer-events: none; }
.ranges { display: flex; gap: 2px; background: var(--track); border-radius: var(--radius-md); padding: 3px; }
.ranges button {
  border: 0; background: transparent; padding: 6px 14px; font-size: 12.5px; color: var(--ink-2);
  border-radius: var(--radius-sm); transition: color 0.15s, transform 0.06s;
}
.ranges button.on { background: var(--surface); color: var(--ink); font-weight: 550; box-shadow: var(--shadow-xs); }
.ranges button:active { transform: scale(0.97); }
.ranges button:focus-visible, .back:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.back { margin-left: auto; color: var(--primary-strong); font-size: 13px; cursor: pointer; transition: color 0.15s ease; }
.back:hover { color: var(--primary-deep); }
.hint { color: var(--ink-2); text-align: center; padding: 18px 0 0; font-size: 14px; }
.chart { height: 280px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-xl); box-shadow: var(--shadow-md); margin-bottom: 14px; }
</style>
