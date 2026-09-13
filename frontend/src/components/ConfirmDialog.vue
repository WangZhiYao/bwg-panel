<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  title: string
  message?: string
  confirmText?: string
  danger?: boolean
  strong?: { label: string; expected: string } | null
  secondaryText?: string
  busy?: boolean
}>(), {
  message: '', confirmText: '确认', danger: false,
  strong: null, secondaryText: '', busy: false,
})

const emit = defineEmits<{ confirm: [typed: string]; cancel: []; secondary: [] }>()

const typed = ref('')
const inputEl = ref<HTMLInputElement | null>(null)
const cancelEl = ref<HTMLButtonElement | null>(null)

const ready = computed(() => !props.strong || typed.value.trim() === props.strong.expected)

watch(() => props.strong, async () => {
  typed.value = ''
  await nextTick()
  // 强确认聚焦输入框；普通模式聚焦「取消」——破坏性操作的默认路径应是放弃
  ;(props.strong ? inputEl.value : cancelEl.value)?.focus()
}, { immediate: true })
</script>

<template>
  <!-- 计划原稿此处为 <Teleport to="body"> 包裹；因 @vue/test-utils 2.4+/2.5 对 Teleport
       stub 绕过转换缓存（vuejs/test-utils#2065），被 stub 的 Teleport 子树每次重渲染
       都整体重建 DOM，测试里跨更新持有的元素引用会失效，本组件的既有测试无法通过。
       故就地渲染：scrim 为 fixed 定位 + z-index 90，当前祖先链无 transform/filter，
       视觉层级与 teleport 版一致。若日后恢复 Teleport，需同步把测试改为每次更新后
       重新查询元素。 -->
  <div class="scrim" @click="!busy && emit('cancel')">
    <div
      class="dialog" role="alertdialog" aria-modal="true" tabindex="-1"
      :aria-label="title" @click.stop @keydown.esc="!busy && emit('cancel')"
    >
      <h3>{{ title }}</h3>
      <p v-if="message" class="msg">{{ message }}</p>
      <input
        v-if="strong" ref="inputEl" v-model="typed" :placeholder="strong.label"
        aria-label="强确认输入"
        @keydown.enter="ready && !busy && emit('confirm', typed)"
      >
      <div class="btns">
        <button ref="cancelEl" class="btn" :disabled="busy" @click="emit('cancel')">取消</button>
        <button v-if="secondaryText" class="secondary" :disabled="busy" @click="emit('secondary')">
          {{ secondaryText }}
        </button>
        <button
          class="btn primary" :class="{ danger }" :disabled="busy || !ready"
          @click="emit('confirm', typed)"
        >{{ busy ? '执行中…' : confirmText }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.scrim {
  position: fixed; inset: 0; z-index: 90;
  background: rgb(23 26 38 / 0.32);
  display: flex; align-items: center; justify-content: center;
}
.dialog {
  width: min(360px, calc(100% - 32px));
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-xl); box-shadow: var(--shadow-lg);
  padding: 22px; display: flex; flex-direction: column; gap: 14px;
}
h3 { margin: 0; font-size: 16px; font-weight: 650; letter-spacing: -0.01em; }
.msg { margin: 0; font-size: 13px; color: var(--ink-2); line-height: 1.6; white-space: pre-line; }
input {
  padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md);
  font-size: 14px; outline: none; transition: border-color 0.15s, box-shadow 0.15s;
}
input:focus { border-color: var(--primary); box-shadow: var(--focus-ring); }
.btns { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.btn {
  padding: 9px 16px; border-radius: var(--radius-md); font-size: 13px;
  border: 1px solid var(--border); background: var(--surface); color: var(--ink-2);
  transition: border-color 0.15s, color 0.15s, transform 0.06s;
}
.btn:not(:disabled):hover { border-color: var(--border-strong); color: var(--ink); }
.btn.primary { background: var(--dark); border-color: var(--dark); color: var(--dark-ink); font-weight: 550; }
.btn.primary.danger { background: var(--danger); border-color: var(--danger); }
.btn:not(:disabled):active { transform: scale(0.97); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.secondary {
  margin-right: auto; border: 0; background: none; padding: 4px 2px;
  font-size: 12.5px; color: var(--danger); cursor: pointer; text-decoration: underline;
  text-underline-offset: 3px;
}
.secondary:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
