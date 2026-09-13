// @vitest-environment node —— 只需读文件比对字符串，无需 DOM；
/// <reference types="node" /> —— tsconfig.app 的 types 白名单不含 node，测试文件显式引入
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { CHART } from './chart-theme'

const css = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8')
const token = (n: string) => css.match(new RegExp(`--${n}:\\s*(#[0-9a-f]{6})`))?.[1]

describe('chart-theme', () => {
  it('五色齐备且为合法 hex', () => {
    for (const v of Object.values(CHART)) {
      expect(v).toMatch(/^#[0-9a-f]{6}$/)
    }
    expect(Object.keys(CHART).sort()).toEqual(['axis', 'grid', 'primary', 'secondary', 'title'])
  })

  it('与 tokens.css 同值（双源同步义务）', () => {
    expect(CHART.primary).toBe(token('primary'))
    expect(CHART.axis).toBe(token('ink-3'))
    expect(CHART.grid).toBe(token('track'))
    expect(CHART.title).toBe(token('ink-2'))
  })
})
