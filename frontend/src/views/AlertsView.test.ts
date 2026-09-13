import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('../api', () => ({
  ApiError: class extends Error { code = 'x' },
  getAlerts: vi.fn(),
  ackAlert: vi.fn(),
}))
import { ackAlert, getAlerts } from '../api'
import type { AlertRow } from '../types'
import AlertsView from './AlertsView.vue'

function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/alerts', component: { template: '<div/>' } }],
  })
  return mount(AlertsView, { global: { plugins: [router], stubs: { TopBar: true } } })
}

const row = (over: Partial<AlertRow> = {}): AlertRow => ({
  id: 1, server_id: 1, server_name: 'Mock-A', type: 'offline', message: '掉线了',
  triggered_at: '2026-09-12T00:00:00+00:00', resolved_at: null, notified: true,
  acknowledged: false, ...over,
})

beforeEach(() => {
  vi.mocked(getAlerts).mockReset().mockResolvedValue([
    row({ id: 2, type: 'traffic_warn', message: '流量 82%' }),
    row({ id: 1, resolved_at: '2026-09-11T00:00:00+00:00', notified: false }),
  ])
})

describe('AlertsView', () => {
  it('未解决置顶 + 历史分区，含类型标签/推送状态/时间', async () => {
    const w = mountView()
    await vi.waitFor(() => expect(w.text()).toContain('流量 82%'))
    expect(w.find('h2').text()).toContain('未解决（1）')
    expect(w.text()).toContain('流量预警')
    expect(w.text()).toContain('历史')
    expect(w.text()).toContain('掉线')       // 历史区的 offline 类型标签
    expect(w.text()).toContain('未推送')
    expect(w.text()).toMatch(/2026-\d{2}-\d{2} \d{2}:\d{2}/)
  })

  it('严重类型行标红（data-level=danger），轻类型为 warn', async () => {
    vi.mocked(getAlerts).mockResolvedValue([
      row({ id: 3, type: 'traffic_warn', message: 'w' }),
      row({ id: 2, type: 'offline', message: 'd' }),
    ])
    const w = mountView()
    await vi.waitFor(() => expect(w.text()).toContain('w'))
    expect(w.findAll('.row')[0].attributes('data-level')).toBe('warn')
    expect(w.findAll('.row')[1].attributes('data-level')).toBe('danger')
  })

  it('空态显示一切正常', async () => {
    vi.mocked(getAlerts).mockResolvedValue([])
    const w = mountView()
    await vi.waitFor(() => expect(w.text()).toContain('暂无告警'))
  })

  it('首载失败显示加载失败，而非误报一切正常', async () => {
    vi.mocked(getAlerts).mockRejectedValue(new Error('x'))
    const w = mountView()
    await vi.waitFor(() => expect(w.text()).toContain('加载失败'))
    expect(w.text()).not.toContain('一切正常')
  })

  it('知道了：调 ackAlert 后行灰化、标已确认、按钮消失', async () => {
    vi.mocked(ackAlert).mockReset().mockResolvedValue({ ok: true })
    const w = mountView()
    await vi.waitFor(() => expect(w.text()).toContain('流量 82%'))
    const activeRow = w.findAll('.row')[0]
    expect(activeRow.classes()).not.toContain('acked')
    await w.findAll('button').find(b => b.text() === '知道了')!.trigger('click')
    expect(ackAlert).toHaveBeenCalledWith(2)
    await vi.waitFor(() => expect(w.text()).toContain('已确认'))
    expect(w.findAll('.row')[0].classes()).toContain('acked')
    expect(w.findAll('button').some(b => b.text() === '知道了')).toBe(false)
  })
})
