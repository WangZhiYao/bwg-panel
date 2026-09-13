import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ServerCard from './ServerCard.vue'
import type { ServerSummary } from '../types'

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  powerServer: vi.fn().mockResolvedValue(undefined),
}))
import { powerServer } from '../api'

const server: ServerSummary = {
  id: 1, name: 'VPS-A', veid: '9000001',
  node_location: 'DC9 CN2', os: 'Debian 12', vm_type: 'kvm',
  ip_addresses: ['104.194.1.1'],
  plan_disk: '20 G', plan_ram: '1.0 G', plan_swap: '256 MB',
  traffic: { used: 337 * 1024 ** 3, quota: 1024 ** 4, next_reset: null },
  latest: {
    id: 1, server_id: 1, ts: new Date().toISOString(), status: 'running',
    data_counter: 337 * 1024 ** 3, disk_used_b: 18.2 * 1024 ** 3, disk_quota_b: 20 * 1024 ** 3,
    mem_available_kb: 612 * 1024, mem_total_kb: 1024 * 1024,
    swap_available_kb: 250_000, swap_total_kb: 262_144, load_average: 0.24, cpu_throttled: 0,
  },
  stale: false,
}

describe('ServerCard', () => {
  it('渲染昵称/机房/IP/运行徽章', () => {
    const w = mount(ServerCard, { props: { server, todayBytes: 1024 ** 3 } })
    expect(w.text()).toContain('VPS-A')
    expect(w.text()).toContain('DC9 CN2')
    expect(w.text()).toContain('104.194.1.1')
    expect(w.text()).toContain('运行中')
  })

  it('quota=0 哨兵 → 环显示 -- 且不显示 0 B', () => {
    const unknown = { ...server, traffic: { used: null, quota: 0, next_reset: null } }
    const w = mount(ServerCard, { props: { server: unknown, todayBytes: null } })
    expect(w.text()).toContain('--')
    expect(w.text()).toContain('未知')
  })

  it('stale=true 显示过期角标', () => {
    const w = mount(ServerCard, { props: { server: { ...server, stale: true }, todayBytes: null } })
    expect(w.text()).toContain('数据可能过期')
  })

  it('点击刷新按钮 emit refresh', async () => {
    const w = mount(ServerCard, { props: { server, todayBytes: null } })
    await w.find('button.solid').trigger('click')
    expect(w.emitted('refresh')).toHaveLength(1)
  })

  it('流量 >=80% 时卡片带 warnring 类', () => {
    const hot = { ...server, traffic: { used: 850 * 1024 ** 3, quota: 1024 ** 4, next_reset: null } }
    const w = mount(ServerCard, { props: { server: hot, todayBytes: null } })
    expect(w.find('.card').classes()).toContain('warnring')
  })

  it('latest 为 null → 无数据徽章', () => {
    const w = mount(ServerCard, { props: { server: { ...server, latest: null }, todayBytes: null } })
    expect(w.text()).toContain('无数据')
  })
})

describe('M3 电源操作', () => {
  it('点重启 → 弹窗 → 确认调 powerServer 并 emit opdone', async () => {
    const w = mount(ServerCard, {
      props: { server, todayBytes: null },
      global: { stubs: { teleport: true } },
    })
    const btn = w.findAll('button').find(b => b.text().includes('重启'))!
    await btn.trigger('click')
    expect(w.find('.dialog').exists()).toBe(true)          // ConfirmDialog 打开
    await w.findAll('button').find(b => b.text() === '确认')!.trigger('click')
    expect(powerServer).toHaveBeenCalledWith(1, 'restart', undefined)
    await vi.waitFor(() => expect(w.emitted('opdone')).toBeTruthy())
  })

  it('关机弹窗的「强制断电…」切换到 kill 强确认；昵称匹配才能提交', async () => {
    const w = mount(ServerCard, {
      props: { server, todayBytes: null },
      global: { stubs: { teleport: true } },
    })
    await w.findAll('button').find(b => b.text().includes('关机'))!.trigger('click')
    await w.findAll('button').find(b => b.text() === '强制断电…')!.trigger('click')
    expect(w.find('input').exists()).toBe(true)            // 强确认输入框
    const ok = w.findAll('button').find(b => b.text() === '强制断电')!
    expect(ok.attributes('disabled')).toBeDefined()
    await w.find('input').setValue('VPS-A')                // server.name = 'VPS-A'
    await ok.trigger('click')
    expect(powerServer).toHaveBeenCalledWith(1, 'kill', 'VPS-A')
  })

  it('停止状态时按钮文案为 开机', () => {
    const stopped = {
      ...server,
      latest: { ...server.latest!, status: 'stopped' },
    }
    const w = mount(ServerCard, { props: { server: stopped, todayBytes: null } })
    expect(w.text()).toContain('开机')
    expect(w.text()).toContain('已关机')                    // statusLabel 映射
  })
})
