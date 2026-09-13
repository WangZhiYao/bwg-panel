<script setup lang="ts">
import { computed } from 'vue'
import { ICONS, type IconName } from '../icons'

const props = withDefaults(defineProps<{ name: IconName; size?: number }>(), { size: 16 })

const markup = computed(() => {
  const m = ICONS[props.name]
  if (!m) {
    console.warn(`[Icon] 未知图标名: ${String(props.name)}`)
    return ''
  }
  return m
})
</script>

<template>
  <svg
    class="icon" :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true"
    fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
  ><g v-html="markup" /></svg>
</template>

<style scoped>
.icon { display: inline-block; vertical-align: -0.125em; flex: none; }
</style>
