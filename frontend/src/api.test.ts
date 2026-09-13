import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, createServer, createSnapshot, deleteServer, deleteSnapshot, getAlerts, getHistory, getServers, getSnapshots, login, powerServer, putSettings, refreshServer, restoreSnapshot, sendTestEmail, updateServer } from './api'

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue(
    new Response(body === null ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  )
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => vi.unstubAllGlobals())

describe('api 封装', () => {
  it('成功返回解析后的 JSON', async () => {
    const fn = mockFetch(200, [{ id: 1, name: 'A', ip_addresses: [] }])
    const list = await getServers()
    expect(list[0].name).toBe('A')
    expect(fn.mock.calls[0][0]).toBe('/api/servers')
  })

  it('非 2xx 抛 ApiError（扁平错误结构）', async () => {
    mockFetch(401, { error: 'bad_credentials', message: '密码错误' })
    const err = await login('x').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.code).toBe('bad_credentials')
    expect(err.message).toBe('密码错误')
  })

  it('响应体非 JSON 时兜底错误', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>', { status: 502 })))
    const err = await login('x').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.code).toBe('bad_response')
  })

  it('POST 请求带 JSON body 与凭证', async () => {
    const fn = mockFetch(200, { ok: true })
    await login('secret')
    const init = fn.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ password: 'secret' })
    expect(init.credentials).toBe('same-origin')
  })

  it('204 无 body 直接返回 undefined（M3 删除端点契约）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    const result = await login('x')
    expect(result).toBeUndefined()
  })

  it('网络 reject 抛原生错误（守卫据此区分）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = await login('x').catch((e) => e)
    expect(err).toBeInstanceOf(TypeError)
    expect(err).not.toBeInstanceOf(ApiError)
  })
})

describe('端点 URL 契约', () => {
  it('refreshServer POST 到 /api/servers/{id}/refresh', async () => {
    const fn = mockFetch(200, { id: 1 })
    await refreshServer(7)
    expect(fn.mock.calls[0][0]).toBe('/api/servers/7/refresh')
    expect((fn.mock.calls[0][1] as RequestInit).method).toBe('POST')
  })

  it('getHistory 拼 range 查询串', async () => {
    const fn = mockFetch(200, { samples: [], daily_usage: [] })
    await getHistory(3, '7d')
    expect(fn.mock.calls[0][0]).toBe('/api/servers/3/history?range=7d')
  })

  it('调用方自定义 headers 不丢 Content-Type（合并式）', async () => {
    const fn = mockFetch(200, { ok: true })
    await login('x').catch(() => {})
    const headers = (fn.mock.calls[0][1] as RequestInit).headers as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
  })
})

describe('M3 端点 URL 契约', () => {
  it('powerServer POST action 与强确认字段', async () => {
    const fn = mockFetch(200, { id: 1 })
    await powerServer(7, 'kill', '东京机')
    expect(fn.mock.calls[0][0]).toBe('/api/servers/7/power')
    const init = fn.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ action: 'kill', confirm_name: '东京机' })
  })

  it('powerServer 无确认时字段为 undefined（序列化省略）', async () => {
    const fn = mockFetch(200, { id: 1 })
    await powerServer(7, 'restart')
    expect(JSON.parse((fn.mock.calls[0][1] as RequestInit).body as string))
      .toEqual({ action: 'restart', confirm_name: undefined })
  })

  it('getSnapshots GET 列表', async () => {
    const fn = mockFetch(200, { snapshots: [] })
    await getSnapshots(7)
    expect(fn.mock.calls[0][0]).toBe('/api/servers/7/snapshots')
  })

  it('createSnapshot POST description', async () => {
    const fn = mockFetch(200, { fileName: 'snapshot-001' })
    await createSnapshot(7, '升级前')
    expect(fn.mock.calls[0][0]).toBe('/api/servers/7/snapshots')
    expect(JSON.parse((fn.mock.calls[0][1] as RequestInit).body as string))
      .toEqual({ description: '升级前' })
  })

  it('deleteSnapshot DELETE 编码文件名', async () => {
    const fn = mockFetch(204, null)
    await deleteSnapshot(7, 'snap 01')
    expect(fn.mock.calls[0][0]).toBe('/api/servers/7/snapshots/snap%2001')
    expect((fn.mock.calls[0][1] as RequestInit).method).toBe('DELETE')
  })

  it('restoreSnapshot POST 强确认字段', async () => {
    const fn = mockFetch(200, { ok: true })
    await restoreSnapshot(7, 'snap 01', '东京机')
    expect(fn.mock.calls[0][0]).toBe('/api/servers/7/snapshots/snap%2001/restore')
    expect(JSON.parse((fn.mock.calls[0][1] as RequestInit).body as string))
      .toEqual({ confirm_name: '东京机' })
  })
})

describe('M4 端点 URL 契约', () => {
  it('getAlerts 拼 active 查询串', async () => {
    const fn = mockFetch(200, [])
    await getAlerts(true)
    expect(fn.mock.calls[0][0]).toBe('/api/alerts?active=1')
    await getAlerts()
    expect(fn.mock.calls[1][0]).toBe('/api/alerts')
  })

  it('putSettings PUT JSON body', async () => {
    const fn = mockFetch(200, {})
    await putSettings({ smtp_host: 'smtp.x.com', smtp_pass: undefined })
    const init = fn.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body as string)).toEqual({ smtp_host: 'smtp.x.com' })
  })

  it('putSettings 空串密码会序列化（显式清除 ≠ 省略保留）', async () => {
    const fn = mockFetch(200, {})
    await putSettings({ smtp_pass: '' })
    expect(JSON.parse((fn.mock.calls[0][1] as RequestInit).body as string)).toEqual({ smtp_pass: '' })
  })

  it('sendTestEmail POST', async () => {
    const fn = mockFetch(200, { ok: true })
    await sendTestEmail()
    expect(fn.mock.calls[0][0]).toBe('/api/settings/test-email')
    expect((fn.mock.calls[0][1] as RequestInit).method).toBe('POST')
  })

  it('createServer POST body', async () => {
    const fn = mockFetch(201, {})
    await createServer({ name: 'A', veid: '1', api_key: 'k' })
    expect(fn.mock.calls[0][0]).toBe('/api/servers')
    expect(JSON.parse((fn.mock.calls[0][1] as RequestInit).body as string))
      .toEqual({ name: 'A', veid: '1', api_key: 'k' })
  })

  it('updateServer PATCH / deleteServer DELETE', async () => {
    const fn = mockFetch(200, {})
    await updateServer(3, { name: 'B' })
    expect(fn.mock.calls[0][0]).toBe('/api/servers/3')
    expect((fn.mock.calls[0][1] as RequestInit).method).toBe('PATCH')
    const fn2 = mockFetch(204, null)
    await deleteServer(3)
    expect(fn2.mock.calls[0][0]).toBe('/api/servers/3')
    expect((fn2.mock.calls[0][1] as RequestInit).method).toBe('DELETE')
  })
})
