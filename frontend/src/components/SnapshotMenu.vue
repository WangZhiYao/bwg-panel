<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { ServerSummary, Snapshot } from '../types'
import { ApiError, createSnapshot, deleteSnapshot, getSnapshots, restoreSnapshot } from '../api'
import { humanBytes, snapshotTime } from '../format'
import ConfirmDialog from './ConfirmDialog.vue'
import Icon from './Icon.vue'
import { toast } from '../toast'

const props = defineProps<{ server: ServerSummary }>()
const emit = defineEmits<{ close: []; changed: [] }>()

const snapshots = ref<Snapshot[] | null>(null)
const errorText = ref('')
const creating = ref(false)
const askDelete = ref<Snapshot | null>(null)
const askRestore = ref<Snapshot | null>(null)
const busyFile = ref('')

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : '网络错误'
}

async function load() {
  errorText.value = ''
  try {
    snapshots.value = (await getSnapshots(props.server.id)).snapshots
  } catch (e) {
    errorText.value = e instanceof ApiError ? e.message : '加载失败'
  }
}

onMounted(load)

async function doCreate() {
  if (creating.value) return
  creating.value = true
  try {
    const r = await createSnapshot(props.server.id, undefined)
    toast(`快照已创建：${r.fileName}`)
    await load()
  } catch (e) {
    toast(errMsg(e), 'danger')
  } finally {
    creating.value = false
  }
}

async function doDelete() {
  const snap = askDelete.value
  if (!snap || busyFile.value) return
  busyFile.value = snap.fileName
  try {
    await deleteSnapshot(props.server.id, snap.fileName)
    toast(`已删除 ${snap.fileName}`)
    askDelete.value = null
    await load()
  } catch (e) {
    toast(errMsg(e), 'danger')
  } finally {
    busyFile.value = ''
  }
}

async function doRestore(typed: string) {
  const snap = askRestore.value
  if (!snap || busyFile.value) return
  busyFile.value = snap.fileName
  try {
    await restoreSnapshot(props.server.id, snap.fileName, typed)
    toast('恢复任务已提交，完成后服务器会自动重启')
    askRestore.value = null
    emit('changed')
    emit('close')
  } catch (e) {
    toast(errMsg(e), 'danger')
  } finally {
    busyFile.value = ''
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="underlay" @click="emit('close')" />
  </Teleport>
  <div class="menu" role="dialog" aria-label="快照管理">
    <header>
      <h4>快照</h4>
      <button class="create" :disabled="creating" @click="doCreate">
        <Icon name="camera" :size="13" />{{ creating ? '创建中…' : '新建' }}
      </button>
    </header>

    <p v-if="snapshots === null && !errorText" class="hint">载入中…</p>
    <p v-else-if="errorText" class="hint">{{ errorText }}</p>
    <p v-else-if="!snapshots!.length" class="hint">还没有快照</p>
    <ul v-else class="list">
      <li v-for="snap in snapshots" :key="snap.fileName" :class="{ busy: busyFile === snap.fileName }">
        <div class="info">
          <b class="num">{{ snap.fileName }}</b>
          <span class="meta">
            {{ snapshotTime(snap.timestamp) }} · {{ humanBytes(snap.size) }}<template v-if="snap.description"> · {{ snap.description }}</template>
          </span>
        </div>
        <div class="ops">
          <button class="op" :disabled="busyFile === snap.fileName" @click="askRestore = snap">恢复</button>
          <button class="op del" :disabled="busyFile === snap.fileName" @click="askDelete = snap">删除</button>
        </div>
      </li>
    </ul>

    <ConfirmDialog
      v-if="askDelete"
      :title="`删除快照 ${askDelete.fileName}？`"
      message="删除后不可恢复。"
      confirm-text="删除" danger :busy="busyFile === askDelete.fileName"
      @confirm="doDelete" @cancel="askDelete = null"
    />
    <ConfirmDialog
      v-if="askRestore"
      :title="`从快照恢复 ${askRestore.fileName}`"
      :message="`恢复会覆盖当前磁盘数据并重启「${server.name}」。`"
      confirm-text="恢复" danger
      :strong="{ label: '输入服务器昵称确认', expected: server.name }"
      :busy="busyFile === askRestore.fileName"
      @confirm="doRestore" @cancel="askRestore = null"
    />
  </div>
</template>

<style scoped>
.underlay { position: fixed; inset: 0; z-index: 15; }
/* z-index 20 会形成层叠上下文：内部 ConfirmDialog 的 scrim(90) 只在本上下文内
   生效（根层等效 20）。当前全局层序 10<15<20<90<99 成立；若日后新增根层
   21–98 的浮层需重排。 */
.menu {
  position: absolute; right: 14px; bottom: 64px; z-index: 20;
  width: min(320px, calc(100vw - 32px));
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-lg);
  padding: 12px; display: flex; flex-direction: column; gap: 8px;
}
header { display: flex; align-items: center; justify-content: space-between; }
h4 { margin: 0; font-size: 13px; font-weight: 650; color: var(--ink-2); }
.create {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 12px; border-radius: var(--radius-md); font-size: 12.5px;
  border: 1px solid var(--border); background: var(--surface); color: var(--ink-2);
  transition: border-color 0.15s, color 0.15s;
}
.create:not(:disabled):hover { border-color: var(--border-strong); color: var(--ink); }
.create:disabled { opacity: 0.55; cursor: default; }
.hint { margin: 0; padding: 14px 0; text-align: center; font-size: 12.5px; color: var(--ink-3); }
.list { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 2px; max-height: 260px; overflow-y: auto; }
li { display: flex; align-items: center; gap: 10px; padding: 8px 6px; border-radius: var(--radius-sm); }
li:not(.busy):hover { background: var(--surface-2); }
li.busy { opacity: 0.55; }
.info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.info b { font-size: 12px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meta { font-size: 11px; color: var(--ink-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ops { display: flex; gap: 4px; flex: none; }
.op {
  padding: 5px 10px; border-radius: var(--radius-sm); font-size: 11.5px;
  border: 1px solid var(--border); background: var(--surface); color: var(--ink-2);
  transition: border-color 0.15s, color 0.15s;
}
.op:not(:disabled):hover { border-color: var(--border-strong); color: var(--ink); }
.op.del:not(:disabled):hover { border-color: var(--danger); color: var(--danger); }
.op:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
