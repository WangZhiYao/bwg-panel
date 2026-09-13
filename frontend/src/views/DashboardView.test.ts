import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('../api', () => ({
  ApiError: class extends Error { code = 'x' },
  getServers: vi.fn(),
  getHistory: vi.fn(),
  getMeta: vi.fn(),
  refreshServer: vi.fn(),
  getAlerts: vi.fn(),
}))
import { getAlerts, getHistory, getMeta, getServers } from '../api'
import type { AlertRow, Meta, ServerSummary } from '../types'
import DashboardView from './DashboardView.vue'

const server = {
  id: 1, name: 'A', veid: '9000001',
  node_location: 'Tokyo', os: 'debian', vm_type: 'kvm',
  ip_addresses: ['192.0.2.1'],
  plan_disk: '20 G', plan_ram: '1.0 G', plan_swap: '256 MB',
  traffic: { used: 1, quota: 1024 ** 4, next_reset: null },
  latest: null, stale: false,
} as unknown as ServerSummary

const meta: Meta = { mock: false, last_sample_at: null, rate_limit: null, version: 'test' }

const row = (over: Partial<AlertRow> = {}): AlertRow => ({
  id: 1, server_id: 1, server_name: 'A', type: 'traffic_warn', message: 'm',
  triggered_at: '2026-09-12T00:00:00+00:00', resolved_at: null, notified: true,
  acknowledged: false, ...over,
})

beforeEach(() => {
  vi.mocked(getServers).mockReset().mockResolvedValue([server])
  vi.mocked(getHistory).mockReset().mockResolvedValue({ samples: [], daily_usage: [] })
  vi.mocked(getMeta).mockReset().mockResolvedValue(meta)
  vi.mocked(getAlerts).mockReset().mockResolvedValue([])
})

function mountDash() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div/>' } }],
  })
  return mount(DashboardView, {
    global: { plugins: [router], stubs: { TopBar: true, ServerCard: true } },
  })
}

describe('DashboardView 告警横幅', () => {
  it('有未解决告警时渲染横幅，严重类型红色', async () => {
    vi.mocked(getAlerts).mockResolvedValue([row({ type: 'offline' })])
    const w = mountDash()
    await vi.waitFor(() => expect(w.find('.banner').exists()).toBe(true))
    expect(w.find('.banner').attributes('data-level')).toBe('danger')
    expect(w.text()).toContain('1 条未解决告警')
  })

  it('仅 warn 级别时横幅黄色', async () => {
    vi.mocked(getAlerts).mockResolvedValue([row({ type: 'traffic_warn' })])
    const w = mountDash()
    await vi.waitFor(() => expect(w.find('.banner').exists()).toBe(true))
    expect(w.find('.banner').attributes('data-level')).toBe('warn')
  })

  it('无未解决告警时无横幅', async () => {
    const w = mountDash()
    await vi.waitFor(() => expect(w.text()).not.toContain('载入中'))
    expect(w.find('.banner').exists()).toBe(false)
  })
})
