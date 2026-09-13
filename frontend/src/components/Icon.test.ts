import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Icon from './Icon.vue'
import { ICONS, type IconName } from '../icons'

describe('Icon', () => {
  it.each(Object.keys(ICONS))('%s 渲染 24 viewBox 的 svg 且装饰性隐藏', (name) => {
    const w = mount(Icon, { props: { name: name as IconName } })
    expect(w.find('svg').attributes('viewBox')).toBe('0 0 24 24')
    expect(w.find('svg').attributes('aria-hidden')).toBe('true')
    // 描边契约：SVG 默认 fill 是黑色，这些属性一旦丢失图标会整体变黑块
    expect(w.find('svg').attributes('fill')).toBe('none')
    expect(w.find('svg').attributes('stroke')).toBe('currentColor')
    expect(w.find('svg').attributes('stroke-width')).toBe('2')
    expect(w.find('svg g').element.innerHTML).not.toBe('')
  })

  it('size prop 生效', () => {
    const w = mount(Icon, { props: { name: 'server', size: 20 } })
    expect(w.find('svg').attributes('width')).toBe('20')
    expect(w.find('svg').attributes('height')).toBe('20')
  })

  it('未知 name 渲染空 svg 并 console.warn', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const w = mount(Icon, { props: { name: 'nope' as unknown as IconName } })
    expect(w.find('svg g').element.innerHTML).toBe('')
    expect(spy).toHaveBeenCalled()
    spy.mockRestore()
  })
})
