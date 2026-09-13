<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, login } from '../api'
import Icon from '../components/Icon.vue'

const router = useRouter()
const password = ref('')
const busy = ref(false)
const errorText = ref('')

async function submit() {
  if (!password.value || busy.value) return
  busy.value = true
  errorText.value = ''
  try {
    await login(password.value)
    router.replace('/')
  } catch (e) {
    errorText.value = e instanceof ApiError ? e.message : '网络错误，请稍后再试'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="page grid-bg">
    <form class="card rise" @submit.prevent="submit">
      <div class="logo"><Icon name="server" :size="20" /></div>
      <h1>BWG 面板</h1>
      <p class="sub">搬瓦工 VPS 监控管理</p>
      <input
        v-model="password" type="password" placeholder="管理员密码" autocomplete="current-password"
        autofocus aria-label="管理员密码"
        :disabled="busy" @input="errorText = ''"
      />
      <p v-if="errorText" class="err" role="alert">{{ errorText }}</p>
      <button type="submit" :disabled="busy || !password">{{ busy ? '登录中…' : '登 录' }}</button>
    </form>
  </div>
</template>

<style scoped>
.page { min-height: 100vh; display: flex; align-items: center; justify-content: center; }
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-lg); padding: 34px; width: min(350px, 100% - 32px); text-align: center;
}
.logo {
  width: 44px; height: 44px; margin: 0 auto; border-radius: var(--radius-lg);
  background: var(--primary-soft); color: var(--primary-deep);
  display: flex; align-items: center; justify-content: center;
}
h1 { margin: 12px 0 2px; font-size: 19px; font-weight: 650; letter-spacing: -0.01em; }
.sub { margin: 0 0 22px; color: var(--ink-3); font-size: 13px; }
input {
  width: 100%; padding: 11px 14px; border: 1px solid var(--border); border-radius: var(--radius-md);
  font-size: 14px; outline: none; transition: border-color 0.15s, box-shadow 0.15s;
}
input:focus { border-color: var(--primary); box-shadow: var(--focus-ring); }
.err { color: var(--danger); font-size: 12.5px; margin: 10px 0 0; }
button {
  width: 100%; margin-top: 16px; padding: 11px 0; border: 0; border-radius: var(--radius-md);
  background: var(--dark); color: var(--dark-ink); font-size: 14px; font-weight: 550;
  transition: transform 0.06s, opacity 0.15s;
}
button:hover:not(:disabled) { opacity: 0.92; }
button:active:not(:disabled) { transform: scale(0.98); }
button:disabled { opacity: 0.55; cursor: default; }
</style>
