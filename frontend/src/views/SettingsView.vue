<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  ApiError, createServer, deleteServer, getSettings, getServers,
  putSettings, sendTestEmail, updateServer,
} from '../api'
import type { PanelSettings, ServerSummary } from '../types'
import { toast } from '../toast'
import TopBar from '../components/TopBar.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const loading = ref(true)
const failed = ref(false)
const saving = ref(false)
const testing = ref(false)
const servers = ref<ServerSummary[]>([])
const passSet = ref(false)

const form = reactive({
  smtp_host: '',
  smtp_port: 465,
  smtp_user: '',
  smtp_pass: '',            // 只写：空 = 不修改
  smtp_from: '',
  smtp_to: '',              // 逗号分隔输入
  threshold_warn: 80,       // 界面百分比，提交转小数
  threshold_critical: 95,
  threshold_disk: 90,
  threshold_mem: 90,
  sample_interval_seconds: 300,
  timezone: 'Asia/Shanghai',
})

function fillForm(s: PanelSettings) {
  form.smtp_host = s.smtp_host
  form.smtp_port = s.smtp_port
  form.smtp_user = s.smtp_user
  form.smtp_from = s.smtp_from
  form.smtp_to = s.smtp_to.join(', ')
  form.threshold_warn = Math.round(s.threshold_warn * 100)
  form.threshold_critical = Math.round(s.threshold_critical * 100)
  form.threshold_disk = Math.round(s.threshold_disk * 100)
  form.threshold_mem = Math.round(s.threshold_mem * 100)
  form.sample_interval_seconds = s.sample_interval_seconds
  form.timezone = s.timezone
  passSet.value = s.smtp_pass_set
}

async function reload() {
  try {
    const [s, list] = await Promise.all([getSettings(), getServers()])
    fillForm(s)
    servers.value = list
    failed.value = false
  } catch {
    failed.value = true
    toast('设置加载失败', 'danger')
  } finally {
    loading.value = false
  }
}

onMounted(reload)

async function save(): Promise<boolean> {
  if (saving.value) return false
  saving.value = true
  try {
    const s = await putSettings({
      smtp_host: form.smtp_host.trim(),
      smtp_port: form.smtp_port,
      smtp_user: form.smtp_user.trim(),
      smtp_pass: form.smtp_pass || undefined,
      smtp_from: form.smtp_from.trim(),
      smtp_to: form.smtp_to.split(/[,，]/).map((x) => x.trim()).filter(Boolean),
      threshold_warn: form.threshold_warn / 100,
      threshold_critical: form.threshold_critical / 100,
      threshold_disk: form.threshold_disk / 100,
      threshold_mem: form.threshold_mem / 100,
      sample_interval_seconds: form.sample_interval_seconds,
      timezone: form.timezone.trim(),
    })
    fillForm(s)
    form.smtp_pass = ''
    toast('设置已保存')
    return true
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '保存失败', 'danger')
    return false
  } finally {
    saving.value = false
  }
}

async function testEmail() {
  if (testing.value) return
  if (!(await save())) return          // 测试前先落库：测的就是表单当前配置
  testing.value = true
  try {
    await sendTestEmail()
    toast('测试邮件已发出，请查收')
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '发送失败', 'danger')
  } finally {
    testing.value = false
  }
}

// ---------- 服务器管理 ----------

const adding = ref(false)
const addForm = reactive({ name: '', veid: '', api_key: '' })

async function addServer() {
  if (adding.value) return
  adding.value = true
  try {
    const s = await createServer({
      name: addForm.name.trim(), veid: addForm.veid.trim(), api_key: addForm.api_key.trim(),
    })
    servers.value.push(s)
    addForm.name = addForm.veid = addForm.api_key = ''
    toast(`已添加 ${s.name}`)
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '添加失败', 'danger')
  } finally {
    adding.value = false
  }
}

const editing = ref<ServerSummary | null>(null)
const editBusy = ref(false)
const editForm = reactive({ name: '', veid: '', api_key: '' })

function startEdit(s: ServerSummary) {
  editing.value = s
  editForm.name = s.name
  editForm.veid = s.veid
  editForm.api_key = ''
}

async function saveEdit() {
  if (!editing.value || editBusy.value) return
  editBusy.value = true
  try {
    const s = await updateServer(editing.value.id, {
      name: editForm.name.trim(),
      veid: editForm.veid.trim(),
      api_key: editForm.api_key.trim() || undefined,
    })
    const i = servers.value.findIndex((x) => x.id === s.id)
    if (i >= 0) servers.value[i] = s
    editing.value = null
    toast('已保存')
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '保存失败', 'danger')
  } finally {
    editBusy.value = false
  }
}

const deleting = ref<ServerSummary | null>(null)
const deleteBusy = ref(false)

async function doDelete() {
  if (!deleting.value || deleteBusy.value) return
  deleteBusy.value = true
  const target = deleting.value          // await 会打断 .value 的类型收窄，先取快照
  try {
    await deleteServer(target.id)
    servers.value = servers.value.filter((x) => x.id !== target.id)
    deleting.value = null
    toast('已删除')
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '删除失败', 'danger')
  } finally {
    deleteBusy.value = false
  }
}
</script>

<template>
  <div class="page grid-bg">
    <TopBar />
    <main>
      <h1>设置</h1>
      <p v-if="loading" class="tip">载入中…</p>
      <p v-else-if="failed" class="tip">
        设置加载失败 —— <a role="button" tabindex="0" @click="reload" @keydown.enter.prevent="reload">重试</a>
      </p>
      <template v-else>
        <form class="card panel" @submit.prevent="save">
          <h2>告警与采样</h2>
          <div class="fields">
            <label>流量预警阈值（%）<input v-model.number="form.threshold_warn" type="number" min="1" max="99" aria-label="预警阈值%" required></label>
            <label>流量超限阈值（%）<input v-model.number="form.threshold_critical" type="number" min="2" max="99" aria-label="超限阈值%" required></label>
            <label>磁盘告警阈值（%）<input v-model.number="form.threshold_disk" type="number" min="50" max="99" aria-label="磁盘阈值%" required></label>
            <label>内存告警阈值（%）<input v-model.number="form.threshold_mem" type="number" min="50" max="99" aria-label="内存阈值%" required></label>
            <label>采样间隔（秒，60–3600）<input v-model.number="form.sample_interval_seconds" type="number" min="60" max="3600" step="10" aria-label="采样间隔秒" required></label>
            <label>时区（日耗分桶）<input v-model="form.timezone" placeholder="Asia/Shanghai" aria-label="时区" required></label>
          </div>
          <h2>邮件通知（SMTP）</h2>
          <div class="fields">
            <label>SMTP 主机<input v-model="form.smtp_host" placeholder="smtp.example.com" aria-label="SMTP 主机"></label>
            <label>端口<input v-model.number="form.smtp_port" type="number" min="1" max="65535" aria-label="SMTP 端口" required></label>
            <label>账号<input v-model="form.smtp_user" placeholder="panel@example.com" aria-label="SMTP 账号"></label>
            <label>密码 / 授权码<input v-model="form.smtp_pass" type="password" :placeholder="passSet ? '已保存，留空保持不变' : '未设置'" autocomplete="new-password" aria-label="SMTP 密码"></label>
            <label>发信地址（留空同账号）<input v-model="form.smtp_from" placeholder="panel@example.com" aria-label="发信地址"></label>
            <label>收件人（逗号分隔）<input v-model="form.smtp_to" placeholder="me@example.com" aria-label="收件人"></label>
          </div>
          <div class="actions">
            <button type="submit" class="btn primary" :disabled="saving">{{ saving ? '保存中…' : '保存设置' }}</button>
            <button type="button" class="btn" :disabled="testing" @click="testEmail">{{ testing ? '发送中…' : '发送测试邮件（先保存）' }}</button>
          </div>
        </form>

        <section class="card">
          <h2>服务器</h2>
          <table class="tbl">
            <thead><tr><th>昵称</th><th>VEID</th><th>API Key</th><th></th></tr></thead>
            <tbody>
              <tr v-for="s in servers" :key="s.id" :class="{ editing: editing && editing.id === s.id }">
                <template v-if="editing && editing.id === s.id">
                  <td><input v-model="editForm.name" aria-label="昵称"></td>
                  <td><input v-model="editForm.veid" aria-label="VEID"></td>
                  <td><input v-model="editForm.api_key" type="password" placeholder="不修改请留空" aria-label="API Key"></td>
                  <td class="ops">
                    <button class="btn primary sm" :disabled="editBusy" @click="saveEdit">保存</button>
                    <button class="btn sm" :disabled="editBusy" @click="editing = null">取消</button>
                  </td>
                </template>
                <template v-else>
                  <td>{{ s.name }}</td>
                  <td class="num">{{ s.veid }}</td>
                  <td class="num">●●●●●●</td>
                  <td class="ops">
                    <button class="btn sm" @click="startEdit(s)">编辑</button>
                    <button class="btn sm danger" @click="deleting = s">删除</button>
                  </td>
                </template>
              </tr>
              <tr v-if="!servers.length"><td colspan="4" class="empty">还没有服务器</td></tr>
            </tbody>
          </table>
          <form class="add" @submit.prevent="addServer">
            <input v-model="addForm.name" placeholder="昵称" aria-label="新服务器昵称" required>
            <input v-model="addForm.veid" placeholder="VEID（数字）" aria-label="新服务器 VEID" required>
            <input v-model="addForm.api_key" placeholder="API Key" aria-label="新服务器 API Key" required>
            <button type="submit" class="btn primary" :disabled="adding">{{ adding ? '添加中…' : '添加' }}</button>
          </form>
        </section>
      </template>
    </main>
    <ConfirmDialog
      v-if="deleting"
      title="删除服务器"
      :message="`将移除「${deleting.name}」的面板档案（不影响 KiwiVM 实机），历史采样与告警一并删除。`"
      confirm-text="删除" danger :busy="deleteBusy"
      @confirm="doDelete" @cancel="deleting = null"
    />
  </div>
</template>

<style scoped>
.page { min-height: 100vh; display: flex; flex-direction: column; }
main { flex: 1; width: min(760px, 100% - 32px); margin: 24px auto 40px; }
h1 { font-size: 18px; font-weight: 650; margin: 4px 0 16px; }
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-xl);
  box-shadow: var(--shadow-sm); padding: 22px; margin-bottom: 18px;
}
h2 { font-size: 14px; font-weight: 650; margin: 0 0 14px; color: var(--ink-2); }
.panel .fields + h2 { margin-top: 20px; } /* 章节间距：字段区块后的标题与上方输入框拉开距离 */
.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; color: var(--ink-2); }
input {
  padding: 9px 12px; border: 1px solid var(--border); border-radius: var(--radius-md);
  font-size: 13.5px; outline: none; transition: border-color 0.15s, box-shadow 0.15s;
}
input:focus { border-color: var(--primary); box-shadow: var(--focus-ring); }
.actions { display: flex; gap: 10px; margin-top: 16px; }
.btn {
  padding: 9px 16px; border-radius: var(--radius-md); font-size: 13px;
  border: 1px solid var(--border); background: var(--surface); color: var(--ink-2);
  display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
  transition: border-color 0.15s, color 0.15s, transform 0.06s;
}
.btn:not(:disabled):hover { border-color: var(--border-strong); color: var(--ink); }
.btn.primary { background: var(--dark); border-color: var(--dark); color: var(--dark-ink); font-weight: 550; }
.btn.danger { color: var(--danger); }
.btn.sm { padding: 6px 10px; font-size: 12.5px; }
.btn:not(:disabled):active { transform: scale(0.97); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th { text-align: left; font-size: 12px; color: var(--ink-3); font-weight: 550; padding: 6px 8px; border-bottom: 1px solid var(--border); }
td { padding: 8px; border-bottom: 1px solid var(--border); }
tr.editing td { background: var(--surface-2); }
tr.editing input { width: 100%; }
.ops { text-align: right; white-space: nowrap; }
.ops .btn + .btn { margin-left: 6px; }
.empty { color: var(--ink-3); text-align: center; padding: 18px 0; }
.add { display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 8px; margin-top: 14px; }
.tip { color: var(--ink-2); text-align: center; padding: 60px 0; font-size: 14px; }
.tip a { color: var(--primary); cursor: pointer; text-decoration: underline; text-underline-offset: 3px; }
@media (max-width: 640px) { .add { grid-template-columns: 1fr; } }
</style>
