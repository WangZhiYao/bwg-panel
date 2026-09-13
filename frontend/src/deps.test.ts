import { describe, expect, it } from 'vitest'
import * as echarts from 'echarts'
import { createRouter, createWebHistory } from 'vue-router'

describe('关键依赖可导入', () => {
  it('echarts 暴露 init/dispose', () => {
    expect(typeof echarts.init).toBe('function')
    expect(typeof (echarts as any).dispose).toBe('function')
  })
  it('vue-router 暴露工厂', () => {
    expect(typeof createRouter).toBe('function')
    expect(typeof createWebHistory).toBe('function')
  })
})
