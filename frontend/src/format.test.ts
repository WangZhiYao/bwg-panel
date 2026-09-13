import { describe, expect, it } from 'vitest'
import { humanBytes, pct, daysUntil, timeAgo, pointsLabel, statusLabel, snapshotTime, alertTypeLabel, formatTs } from './format'

describe('humanBytes（1024 进制）', () => {
  it('各量级（尾零省略：1.00→1、1.50→1.5、337.00→337）', () => {
    expect(humanBytes(0)).toBe('0 B')
    expect(humanBytes(1023)).toBe('1023 B')
    expect(humanBytes(1024)).toBe('1 KB')
    expect(humanBytes(337 * 1024 ** 3)).toBe('337 GB')
    expect(humanBytes(1.5 * 1024 ** 4)).toBe('1.5 TB')
  })
  it('null 与 undefined 安全', () => {
    expect(humanBytes(null)).toBe('--')
    expect(humanBytes(undefined as unknown as number)).toBe('--')
  })
  it('非整 GB 保留两位', () => {
    expect(humanBytes(1.234 * 1024 ** 3)).toBe('1.23 GB')
  })
})

describe('pct（用量百分比，quota=0 哨兵→null）', () => {
  it('正常计算', () => { expect(pct(250, 1000)).toBe(25) })
  it('quota<=0 或 used=null → null（未知，不画进度）', () => {
    expect(pct(100, 0)).toBeNull()
    expect(pct(null, 1000)).toBeNull()
  })
  it('超配额封顶 100', () => { expect(pct(2000, 1000)).toBe(100) })
})

describe('daysUntil（重置倒计时）', () => {
  it('未来日期', () => {
    const future = new Date(Date.now() + 12 * 86400_000).toISOString()
    expect(daysUntil(future)).toBe('12 天后重置')
  })
  it('今天', () => {
    expect(daysUntil(new Date().toISOString())).toBe('今天重置')
  })
  it('null 安全', () => { expect(daysUntil(null)).toBe('') })
})

describe('timeAgo（采样新鲜度）', () => {
  it('分钟', () => {
    expect(timeAgo(Date.now() / 1000 - 180)).toBe('3 分钟前采样')
  })
  it('null', () => { expect(timeAgo(null)).toBe('尚未采样') })
})

describe('timeAgo 粒度', () => {
  it('90 秒 → 1 分钟（floor 不漂移）', () => {
    expect(timeAgo(Date.now() / 1000 - 90)).toBe('1 分钟前采样')
  })
  it('49.5 小时 → 2 天前', () => {
    expect(timeAgo(Date.now() / 1000 - 49.5 * 3600)).toBe('2 天前采样')
  })
})

describe('pointsLabel（绝对点数，无总量）', () => {
  it('有缓存', () => {
    expect(pointsLabel({ remaining_points_15min: 800 })).toBe('点数 800/15min')
  })
  it('无缓存', () => { expect(pointsLabel(null)).toBe('点数未知') })
})

describe('statusLabel', () => {
  it('已知状态映射中文', () => {
    expect(statusLabel('running')).toBe('运行中')
    expect(statusLabel('stopped')).toBe('已关机')
    expect(statusLabel('suspended')).toBe('已暂停')
    expect(statusLabel('maintenance')).toBe('维护中')
  })
  it('未知状态原样透传，空值显示无数据', () => {
    expect(statusLabel('weird-state')).toBe('weird-state')
    expect(statusLabel(null)).toBe('无数据')
    expect(statusLabel(undefined)).toBe('无数据')
  })
})

describe('snapshotTime', () => {
  it('unix 秒转 MM-DD HH:mm', () => {
    const d = new Date(2026, 8, 12, 9, 5)          // 本地时区 2026-09-12 09:05
    expect(snapshotTime(Math.floor(d.getTime() / 1000))).toBe('09-12 09:05')
  })
  it('空值显示 --', () => {
    expect(snapshotTime(null)).toBe('--')
  })
})

describe('M4 format 扩展', () => {
  it('formatTs 格式化 ISO 为本地时间串', () => {
    expect(formatTs('2026-09-12T04:05:00+00:00')).toMatch(/^2026-\d{2}-\d{2} \d{2}:\d{2}$/)
  })
  it('formatTs 容错空与非法值', () => {
    expect(formatTs(null)).toBe('--')
    expect(formatTs('not-a-date')).toBe('--')
  })
  it('alertTypeLabel 已知与未知类型', () => {
    expect(alertTypeLabel('offline')).toBe('掉线')
    expect(alertTypeLabel('cpu_throttle')).toBe('CPU 节流')
    expect(alertTypeLabel('weird')).toBe('weird')
  })
})
