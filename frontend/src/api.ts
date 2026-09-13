export class ApiError extends Error {
  code: string
  constructor(code: string, message: string) { super(message); this.code = code }
}

import type { AlertRow, HistoryRange, HistoryResult, Meta, PanelSettings, PowerAction, ServerSummary, SettingsUpdate, Snapshot } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    credentials: 'same-origin',
  })
  if (resp.status === 204) return undefined as T
  const data = await resp.json().catch(() => ({ error: 'bad_response', message: '响应解析失败' }))
  if (!resp.ok) throw new ApiError(data.error ?? 'http_' + resp.status, data.message ?? '请求失败')
  return data as T
}

export async function me() { return request<{ user: string }>('/api/auth/me') }
export async function login(password: string) { return request<{ ok: boolean }>('/api/auth/login', { method: 'POST', body: JSON.stringify({ password }) }) }
export async function logout() { return request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }) }
export async function getServers() { return request<ServerSummary[]>('/api/servers') }
export async function refreshServer(id: number) { return request<ServerSummary>(`/api/servers/${id}/refresh`, { method: 'POST' }) }
export async function getHistory(id: number, range: HistoryRange) { return request<HistoryResult>(`/api/servers/${id}/history?range=${range}`) }
export async function getMeta() { return request<Meta>('/api/meta') }

export async function powerServer(id: number, action: PowerAction, confirmName?: string) {
  return request<ServerSummary>(`/api/servers/${id}/power`, {
    method: 'POST', body: JSON.stringify({ action, confirm_name: confirmName }),
  })
}
export async function getSnapshots(id: number) {
  return request<{ snapshots: Snapshot[] }>(`/api/servers/${id}/snapshots`)
}
export async function createSnapshot(id: number, description?: string) {
  return request<{ fileName: string }>(`/api/servers/${id}/snapshots`, {
    method: 'POST', body: JSON.stringify({ description }),
  })
}
export async function deleteSnapshot(id: number, fileName: string) {
  return request<void>(`/api/servers/${id}/snapshots/${encodeURIComponent(fileName)}`, {
    method: 'DELETE',
  })
}
export async function restoreSnapshot(id: number, fileName: string, confirmName: string) {
  return request<{ ok: boolean }>(`/api/servers/${id}/snapshots/${encodeURIComponent(fileName)}/restore`, {
    method: 'POST', body: JSON.stringify({ confirm_name: confirmName }),
  })
}

// ---------- M4：告警 / 设置 / 服务器管理 ----------

export async function getAlerts(active = false) {
  return request<AlertRow[]>(`/api/alerts${active ? '?active=1' : ''}`)
}
export async function ackAlert(id: number) {
  return request<{ ok: boolean }>(`/api/alerts/${id}/ack`, { method: 'POST' })
}
export async function getSettings() { return request<PanelSettings>('/api/settings') }
export async function putSettings(body: SettingsUpdate) {
  return request<PanelSettings>('/api/settings', { method: 'PUT', body: JSON.stringify(body) })
}
export async function sendTestEmail() {
  return request<{ ok: boolean }>('/api/settings/test-email', { method: 'POST' })
}
export async function createServer(body: { name: string; veid: string; api_key: string }) {
  return request<ServerSummary>('/api/servers', { method: 'POST', body: JSON.stringify(body) })
}
export async function updateServer(id: number, body: { name?: string; veid?: string; api_key?: string }) {
  return request<ServerSummary>(`/api/servers/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
}
export async function deleteServer(id: number) {
  return request<void>(`/api/servers/${id}`, { method: 'DELETE' })
}
