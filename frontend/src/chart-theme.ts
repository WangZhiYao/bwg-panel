/** ECharts canvas 侧唯一色源（canvas 读不到 CSS 变量，双源为必然）。
 *  与 tokens.css 的同步义务由 chart-theme.test.ts 强制：
 *  primary=--primary, axis=--ink-3, grid=--track, title=--ink-2。 */
export const CHART = {
  primary: '#2e7ef2',
  secondary: '#12a169', // 磁盘线：chart 专用色，无同名 token
  axis: '#8a90a5',
  grid: '#eef0f6',
  title: '#4b5165',
} as const
