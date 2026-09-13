<script setup lang="ts">
import { computed } from 'vue'
import { pct } from '../format'

const props = defineProps<{ used: number | null; quota: number }>()

const percent = computed(() => pct(props.used, props.quota)) // 已用百分比；null=未知
const remain = computed(() => (percent.value === null ? null : 100 - percent.value))
const color = computed(() => {
  if (percent.value === null) return 'var(--ink-3)'
  if (percent.value >= 95) return 'var(--danger)'
  if (percent.value >= 80) return 'var(--warn-strong)'
  return 'var(--primary)'
})
const style = computed(() => {
  // background 必须引用 var(--p)（而非内插数值）：@property 注册后 --p 过渡才会驱动环重绘
  return {
    background:
      `conic-gradient(${color.value} 0 calc(var(--p) * 1%), var(--ring-track) calc(var(--p) * 1%) 100%)`,
    '--p': String(percent.value ?? 0),
  } as Record<string, string>
})
</script>

<template>
  <div class="ring" :style="style">
    <div class="inner">
      <b v-if="remain !== null" class="num">{{ remain }}%</b>
      <b v-else class="num">--</b>
      <span class="cap">剩余</span>
    </div>
  </div>
</template>

<style scoped>
.ring {
  width: 72px; height: 72px; border-radius: 50%; flex: none;
  display: flex; align-items: center; justify-content: center;
  transition: --p 0.6s ease;
}
.inner {
  width: 56px; height: 56px; border-radius: 50%; background: var(--surface);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
}
b { font-size: 15px; line-height: 1.1; }
.cap { font-size: 10px; color: var(--ink-3); }
</style>
