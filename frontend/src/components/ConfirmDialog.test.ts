import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ConfirmDialog from './ConfirmDialog.vue'

const stubs = { teleport: true }  // Teleport 就地渲染，便于查询

describe('ConfirmDialog', () => {
  it('渲染标题/正文/按钮并 emit cancel', async () => {
    const w = mount(ConfirmDialog, {
      props: { title: '重启服务器', message: '确定重启？' },
      global: { stubs },
    })
    expect(w.text()).toContain('重启服务器')
    expect(w.text()).toContain('确定重启？')
    await w.findAll('button').find(b => b.text() === '取消')!.trigger('click')
    expect(w.emitted('cancel')).toHaveLength(1)
  })

  it('普通模式确认按钮可用并 emit confirm(typed)', async () => {
    const w = mount(ConfirmDialog, { props: { title: 'T' }, global: { stubs } })
    const ok = w.findAll('button').find(b => b.text() === '确认')!
    expect(ok.attributes('disabled')).toBeUndefined()
    await ok.trigger('click')
    expect(w.emitted('confirm')).toEqual([['']])
  })

  it('强确认：输入不匹配禁用、匹配后 emit 输入值', async () => {
    const w = mount(ConfirmDialog, {
      props: { title: 'T', strong: { label: '服务器昵称', expected: 'Mock-A' } },
      global: { stubs },
    })
    const ok = w.findAll('button').find(b => b.text() === '确认')!
    expect(ok.attributes('disabled')).toBeDefined()
    await w.find('input').setValue('Mock-')
    expect(ok.attributes('disabled')).toBeDefined()
    await w.find('input').setValue('Mock-A')
    expect(ok.attributes('disabled')).toBeUndefined()
    await ok.trigger('click')
    expect(w.emitted('confirm')).toEqual([['Mock-A']])
  })

  it('强确认 trim 后比对（尾随空格放行）', async () => {
    const w = mount(ConfirmDialog, {
      props: { title: 'T', strong: { label: 'n', expected: 'Mock-A' } },
      global: { stubs },
    })
    await w.find('input').setValue(' Mock-A ')
    await w.findAll('button').find(b => b.text() === '确认')!.trigger('click')
    expect(w.emitted('confirm')).toEqual([[' Mock-A ']])
  })

  it('secondary 按钮独立 emit；busy 禁用全部', async () => {
    const w = mount(ConfirmDialog, {
      props: { title: 'T', secondaryText: '强制断电…', busy: true },
      global: { stubs },
    })
    const btns = w.findAll('button')
    for (const b of btns) expect(b.attributes('disabled')).toBeDefined()
    await w.setProps({ busy: false })
    await btns.find(b => b.text() === '强制断电…')!.trigger('click')
    expect(w.emitted('secondary')).toHaveLength(1)
  })
})

describe('ConfirmDialog 键盘与模态语义', () => {
  it('对话框级 Esc 取消；aria-modal 语义就位', async () => {
    const w = mount(ConfirmDialog, { props: { title: 'T' }, global: { stubs } })
    expect(w.find('.dialog').attributes('aria-modal')).toBe('true')
    expect(w.find('.dialog').attributes('role')).toBe('alertdialog')
    await w.find('.dialog').trigger('keydown.esc')
    expect(w.emitted('cancel')).toHaveLength(1)
  })

  it('点击遮罩取消，点击对话框本体不取消', async () => {
    const w = mount(ConfirmDialog, { props: { title: 'T' }, global: { stubs } })
    await w.find('.dialog').trigger('click')
    expect(w.emitted('cancel')).toBeUndefined()
    await w.find('.scrim').trigger('click')
    expect(w.emitted('cancel')).toHaveLength(1)
  })

  it('强确认 Enter：未就绪不提交，就绪后提交', async () => {
    const w = mount(ConfirmDialog, {
      props: { title: 'T', strong: { label: 'n', expected: 'Mock-A' } },
      global: { stubs },
    })
    await w.find('input').setValue('Mock-')
    await w.find('input').trigger('keydown.enter')
    expect(w.emitted('confirm')).toBeUndefined()
    await w.find('input').setValue('Mock-A')
    await w.find('input').trigger('keydown.enter')
    expect(w.emitted('confirm')).toEqual([['Mock-A']])
  })
})
