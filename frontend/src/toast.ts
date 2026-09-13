import { reactive } from 'vue'

export interface Toast { id: number; text: string; kind: 'ok' | 'warn' | 'danger' }

let seq = 1
export const toasts = reactive<Toast[]>([])

export function toast(text: string, kind: Toast['kind'] = 'ok') {
  const id = seq++
  toasts.push({ id, text, kind })
  setTimeout(() => {
    const i = toasts.findIndex((t) => t.id === id)
    if (i >= 0) toasts.splice(i, 1)
  }, 3200)
}
