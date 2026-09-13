import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('../api', () => ({
  ApiError: class extends Error { code = 'x' },
  logout: vi.fn(),
  getAlerts: vi.fn(),
}))
import { getAlerts } from '../api'
import type { AlertRow } from '../types'
import TopBar from './TopBar.vue'

function mountBar() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div/>' } },
      { path: '/alerts', component: { template: '<div/>' } },
      { path: '/settings', component: { template: '<div/>' } },
      { path: '/trends', component: { template: '<div/>' } },
    ],
  })
  return mount(TopBar, { global: { plugins: [router] } })
}

const row = (over: Partial<AlertRow> = {}): AlertRow => ({
  id: 1, server_id: 1, server_name: 'A', type: 'offline', message: 'm',
  triggered_at: '2026-09-12T00:00:00+00:00', resolved_at: null, notified: true,
  acknowledged: false, ...over,
})

beforeEach(() => {
  vi.mocked(getAlerts).mockReset().mockResolvedValue([row()])
})

describe('TopBar', () => {
  it('挂载即轮询未解决告警数并渲染角标', async () => {
    const w = mountBar()
    await vi.waitFor(() => expect(w.find('.badge').exists()).toBe(true))
    expect(w.find('.badge').text()).toBe('1')
    expect(getAlerts).toHaveBeenCalledWith(true)
  })

  it('无未解决告警时不显示角标，但设置/告警入口常驻', async () => {
    vi.mocked(getAlerts).mockResolvedValue([])
    const w = mountBar()
    await vi.waitFor(() => expect(w.text()).toContain('设置'))
    expect(w.find('.badge').exists()).toBe(false)
    expect(w.text()).toContain('趋势')
  })

  it('角标超过 99 显示 99+', async () => {
    vi.mocked(getAlerts).mockResolvedValue(
      Array.from({ length: 120 }, (_, i) => row({ id: i + 1 })))
    const w = mountBar()
    await vi.waitFor(() => expect(w.find('.badge').text()).toBe('99+'))
  })

  it('60s 轮询重拉，卸载后停止（无泄漏）', () => {
    vi.useFakeTimers()
    try {
      const w = mountBar()
      expect(getAlerts).toHaveBeenCalledTimes(1)     // 挂载即拉
      vi.advanceTimersByTime(60_000)
      expect(getAlerts).toHaveBeenCalledTimes(2)     // 周期重拉
      w.unmount()
      vi.advanceTimersByTime(180_000)
      expect(getAlerts).toHaveBeenCalledTimes(2)     // 卸载后不再拉
    } finally {
      vi.useRealTimers()
    }
  })
})
