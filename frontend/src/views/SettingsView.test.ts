import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('../api', () => ({
  ApiError: class extends Error { code = 'x' },
  logout: vi.fn(),
  getAlerts: vi.fn().mockResolvedValue([]),
  getSettings: vi.fn(),
  getServers: vi.fn(),
  putSettings: vi.fn(),
  sendTestEmail: vi.fn(),
  createServer: vi.fn(),
  updateServer: vi.fn(),
  deleteServer: vi.fn(),
}))
import { createServer, deleteServer, getSettings, getServers, putSettings, sendTestEmail, updateServer } from '../api'
import type { PanelSettings, ServerSummary } from '../types'
import SettingsView from './SettingsView.vue'

const settings: PanelSettings = {
  smtp_host: 'smtp.example.com', smtp_port: 465, smtp_user: 'panel@x.com',
  smtp_from: '', smtp_to: ['a@x.com', 'b@x.com'],
  threshold_warn: 0.8, threshold_critical: 0.95,
  sample_interval_seconds: 300, timezone: 'Asia/Shanghai',
  smtp_pass_set: false,
}

const server = {
  id: 1, name: '东京机', veid: '9000001',
  node_location: null, os: null, vm_type: null, ip_addresses: [],
  plan_disk: null, plan_ram: null, plan_swap: null,
  traffic: { used: null, quota: 0, next_reset: null },
  latest: null, stale: true,
} as unknown as ServerSummary

beforeEach(() => {
  vi.mocked(getSettings).mockReset().mockResolvedValue({ ...settings })
  vi.mocked(getServers).mockReset().mockResolvedValue([server])
  vi.mocked(putSettings).mockReset().mockResolvedValue({ ...settings })
  vi.mocked(sendTestEmail).mockReset().mockResolvedValue({ ok: true })
  vi.mocked(createServer).mockReset().mockResolvedValue(server)
  vi.mocked(deleteServer).mockReset().mockResolvedValue(undefined)
})

function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/settings', component: { template: '<div/>' } }],
  })
  return mount(SettingsView, { global: { plugins: [router], stubs: { TopBar: true } } })
}

const input = (w: ReturnType<typeof mountView>, label: string) =>
  w.find(`input[aria-label="${label}"]`)

describe('SettingsView', () => {
  it('加载渲染：SMTP 值、收件人逗号串、阈值百分比、服务器表', async () => {
    const w = mountView()
    await vi.waitFor(() => expect((input(w, 'SMTP 主机').element as HTMLInputElement).value).toBe('smtp.example.com'))
    expect((input(w, '收件人').element as HTMLInputElement).value).toBe('a@x.com, b@x.com')
    expect((input(w, '预警阈值%').element as HTMLInputElement).value).toBe('80')
    expect(w.text()).toContain('东京机')
    expect(w.text()).toContain('9000001')
  })

  it('保存：阈值转小数、收件人拆数组、空密码字段省略', async () => {
    const w = mountView()
    await vi.waitFor(() => expect((input(w, 'SMTP 主机').element as HTMLInputElement).value).toBe('smtp.example.com'))
    await w.find('form.panel button[type="submit"]').trigger('submit')
    await vi.waitFor(() => expect(putSettings).toHaveBeenCalled())
    const body = vi.mocked(putSettings).mock.calls[0][0]
    expect(body.threshold_warn).toBe(0.8)
    expect(body.threshold_critical).toBe(0.95)
    expect(body.smtp_to).toEqual(['a@x.com', 'b@x.com'])
    expect(body.smtp_pass).toBeUndefined()
  })

  it('测试邮件：先保存，保存失败则不发', async () => {
    const w = mountView()
    await vi.waitFor(() => expect((input(w, 'SMTP 主机').element as HTMLInputElement).value).toBe('smtp.example.com'))
    await w.findAll('button').find(b => b.text().includes('发送测试邮件'))!.trigger('click')
    await vi.waitFor(() => expect(sendTestEmail).toHaveBeenCalled())
    expect(putSettings).toHaveBeenCalled()

    vi.mocked(sendTestEmail).mockClear()
    vi.mocked(putSettings).mockClear()
    vi.mocked(putSettings).mockRejectedValueOnce(
      Object.assign(new Error('校验失败'), { code: 'invalid_threshold' }) as never)
    await w.findAll('button').find(b => b.text().includes('发送测试邮件'))!.trigger('click')
    await vi.waitFor(() => expect(putSettings).toHaveBeenCalled())
    expect(sendTestEmail).not.toHaveBeenCalled()
  })

  it('添加服务器：填表提交后调 createServer', async () => {
    const w = mountView()
    await vi.waitFor(() => expect(w.text()).toContain('东京机'))
    await input(w, '新服务器昵称').setValue('新机器')
    await input(w, '新服务器 VEID').setValue('9000003')
    await input(w, '新服务器 API Key').setValue('key3')
    await w.find('form.add button[type="submit"]').trigger('submit')
    await vi.waitFor(() => expect(createServer).toHaveBeenCalledWith(
      { name: '新机器', veid: '9000003', api_key: 'key3' }))
    expect(w.text()).toContain('9000001')  // 列表仍在
  })

  it('删除服务器走确认弹窗，确认后调 deleteServer', async () => {
    const w = mountView()
    await vi.waitFor(() => expect(w.text()).toContain('东京机'))
    await w.findAll('button').find(b => b.text() === '删除')!.trigger('click')
    await vi.waitFor(() => expect(w.text()).toContain('删除服务器'))
    await w.findAll('button').find(b => b.text() === '删除' && b.element.closest('.btns') !== null)!.trigger('click')
    await vi.waitFor(() => expect(deleteServer).toHaveBeenCalledWith(1))
  })

  it('编辑服务器：预填、api_key 留空=不改，保存后行更新', async () => {
    vi.mocked(updateServer).mockReset().mockResolvedValue({
      ...server, name: '改名机',
    } as unknown as ServerSummary)
    const w = mountView()
    await vi.waitFor(() => expect(w.text()).toContain('东京机'))
    await w.findAll('button').find(b => b.text() === '编辑')!.trigger('click')
    const name = w.find('input[aria-label="昵称"]')
    expect((name.element as HTMLInputElement).value).toBe('东京机')
    expect((w.find('input[aria-label="API Key"]').element as HTMLInputElement).value).toBe('')
    await name.setValue('改名机')
    await w.findAll('button').find(b => b.text() === '保存' && b.element.closest('.ops') !== null)!.trigger('click')
    await vi.waitFor(() => expect(updateServer).toHaveBeenCalledWith(1, {
      name: '改名机', veid: '9000001', api_key: undefined,
    }))
    await vi.waitFor(() => expect(w.text()).toContain('改名机'))
  })
})
