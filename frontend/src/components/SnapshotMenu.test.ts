import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SnapshotMenu from './SnapshotMenu.vue'
import type { ServerSummary } from '../types'

vi.mock('../api', () => ({
  ApiError: class extends Error { code = 'x' },
  getSnapshots: vi.fn(),
  createSnapshot: vi.fn(),
  deleteSnapshot: vi.fn(),
  restoreSnapshot: vi.fn(),
}))

import { createSnapshot, deleteSnapshot, getSnapshots, restoreSnapshot } from '../api'

const server = { id: 1, name: 'Mock-A' } as unknown as ServerSummary

function mountMenu() {
  return mount(SnapshotMenu, { props: { server }, global: { stubs: { teleport: true } } })
}

beforeEach(() => {
  vi.mocked(getSnapshots).mockReset().mockResolvedValue({
    snapshots: [{
      fileName: 'snapshot-001', timestamp: 1700000000, status: 'complete',
      description: '升级前', size: 1024 ** 3,
    }],
  })
  vi.mocked(createSnapshot).mockReset().mockResolvedValue({ fileName: 'snapshot-002' })
  vi.mocked(deleteSnapshot).mockReset().mockResolvedValue(undefined)
  vi.mocked(restoreSnapshot).mockReset().mockResolvedValue({ ok: true })
})

describe('SnapshotMenu', () => {
  it('挂载即拉取并渲染快照列表', async () => {
    const w = mountMenu()
    await vi.waitFor(() => expect(w.text()).toContain('snapshot-001'))
    expect(w.text()).toContain('升级前')
    expect(w.text()).toContain('1 GB')
  })

  it('新建调 createSnapshot 后刷新列表', async () => {
    vi.mocked(getSnapshots).mockResolvedValueOnce({ snapshots: [] })
    const w = mountMenu()
    await vi.waitFor(() => expect(w.text()).toContain('还没有快照'))
    await w.find('button.create').trigger('click')
    expect(createSnapshot).toHaveBeenCalledWith(1, undefined)
    await vi.waitFor(() => expect(w.text()).toContain('snapshot-001'))
  })

  it('删除走确认弹窗，确认后调 deleteSnapshot 并刷新', async () => {
    const w = mountMenu()
    await vi.waitFor(() => expect(w.text()).toContain('snapshot-001'))
    await w.findAll('button').find(b => b.text() === '删除')!.trigger('click')
    await vi.waitFor(() => expect(w.text()).toContain('删除快照'))
    await w.findAll('button').find(b => b.text() === '删除' && b.element.closest('.btns') !== null)!.trigger('click')
    expect(deleteSnapshot).toHaveBeenCalledWith(1, 'snapshot-001')
  })

  it('恢复需强确认：昵称匹配才可提交，成功后 emit changed + close', async () => {
    const w = mountMenu()
    await vi.waitFor(() => expect(w.text()).toContain('snapshot-001'))
    await w.findAll('button').find(b => b.text() === '恢复')!.trigger('click')
    await vi.waitFor(() => expect(w.find('input').exists()).toBe(true))
    const ok = w.findAll('button').filter(b => b.text() === '恢复' && b.element.closest('.btns') !== null)[0]
    expect(ok.attributes('disabled')).toBeDefined()
    await w.find('input').setValue('Mock-A')
    expect(ok.attributes('disabled')).toBeUndefined()
    await ok.trigger('click')
    expect(restoreSnapshot).toHaveBeenCalledWith(1, 'snapshot-001', 'Mock-A')
    expect(w.emitted('changed')).toHaveLength(1)
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('加载失败显示错误文案', async () => {
    vi.mocked(getSnapshots).mockRejectedValueOnce(new Error('network'))
    const w = mountMenu()
    await vi.waitFor(() => expect(w.text()).toContain('加载失败'))
  })
})

describe('SnapshotMenu 失败路径', () => {
  it('恢复失败：toast 走 danger，不 emit changed/close，弹窗保持', async () => {
    vi.mocked(restoreSnapshot).mockRejectedValueOnce(new Error('boom'))
    const w = mountMenu()
    await vi.waitFor(() => expect(w.text()).toContain('snapshot-001'))
    await w.findAll('button').find(b => b.text() === '恢复')!.trigger('click')
    await vi.waitFor(() => expect(w.find('input').exists()).toBe(true))
    await w.find('input').setValue('Mock-A')
    await w.findAll('button').filter(b => b.text() === '恢复' && b.element.closest('.btns') !== null)[0].trigger('click')
    await vi.waitFor(() => expect(restoreSnapshot).toHaveBeenCalled())
    expect(w.emitted('changed')).toBeUndefined()
    expect(w.emitted('close')).toBeUndefined()
    expect(w.text()).toContain('从快照恢复')          // 弹窗仍在
  })
})
