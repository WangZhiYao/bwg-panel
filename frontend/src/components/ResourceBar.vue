<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ label: string; used: number | null; total: number | null }>()

const ratio = computed(() => {
  if (props.used === null || props.total === null || props.total <= 0) return null
  return Math.min(1, props.used / props.total)
})
const color = computed(() => {
  if (ratio.value === null) return 'var(--ink-3)'
  if (ratio.value >= 0.9) return 'var(--danger)'
  if (ratio.value >= 0.75) return 'var(--warn-strong)'
  return 'var(--primary)'
})
</script>

<template>
  <div class="bar-row">
    <span class="label">{{ label }}</span>
    <div class="track"><div class="fill" :style="{ width: (ratio ?? 0) * 100 + '%', background: color }" /></div>
  </div>
</template>

<style scoped>
.bar-row { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--ink-3); }
.label { width: 32px; flex: none; }
.track { flex: 1; height: 6px; background: var(--track); border-radius: 99px; overflow: hidden; }
.fill { height: 100%; border-radius: 99px; transition: width 0.5s ease; }
</style>
