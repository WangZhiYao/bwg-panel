const UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']

export function humanBytes(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '--'
  let v = Math.max(0, n)
  let i = 0
  while (v >= 1024 && i < UNITS.length - 1) { v /= 1024; i++ }
  // B 取整；其余两位小数并省略尾零（1.00→1 / 1.50→1.5 / 337.00→337）
  const text = i === 0 ? String(Math.round(v)) : v.toFixed(2).replace(/\.?0+$/, '')
  return `${text} ${UNITS[i]}`
}

export function pct(used: number | null, quota: number): number | null {
  if (used === null || Number.isNaN(used) || quota <= 0) return null
  return Math.min(100, Math.round((used / quota) * 100))
}

export function daysUntil(iso: string | null): string {
  if (!iso) return ''
  const ms = new Date(iso).getTime() - Date.now()
  if (Number.isNaN(ms)) return ''
  const days = Math.ceil(ms / 86400_000)
  if (days <= 0) return '今天重置'
  return `${days} 天后重置`
}

export function timeAgo(unixSeconds: number | null): string {
  if (!unixSeconds) return '尚未采样'
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - unixSeconds))
  if (sec < 60) return '刚刚采样'
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} 分钟前采样`
  const hr = Math.floor(min / 60)
  if (hr < 48) return `${hr} 小时前采样`
  const day = Math.floor(hr / 24)
  return `${day} 天前采样`
}

export function pointsLabel(rl: { remaining_points_15min?: number } | null | undefined): string {
  return rl && typeof rl.remaining_points_15min === 'number'
    ? `点数 ${rl.remaining_points_15min}/15min`
    : '点数未知'
}

const STATUS_LABELS: Record<string, string> = {
  running: '运行中',
  stopped: '已关机',
  suspended: '已暂停',
  maintenance: '维护中',
}

export function statusLabel(s: string | null | undefined): string {
  if (!s) return '无数据'
  return STATUS_LABELS[s] ?? s
}

export function snapshotTime(unix: number | null | undefined): string {
  if (!unix) return '--'
  const d = new Date(unix * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export function formatTs(iso: string | null | undefined): string {
  if (!iso) return '--'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '--'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// 与后端 alerter.TYPE_LABELS 同值两份（前后端无法共享常量）；新增告警类型时两侧同步
const ALERT_TYPE_LABELS: Record<string, string> = {
  offline: '掉线',
  traffic_warn: '流量预警',
  traffic_critical: '流量超限预警',
  disk_high: '磁盘空间告警',
  mem_high: '内存告警',
  cpu_throttle: 'CPU 节流',
  collect_error: '采集失败',
  email_error: '邮件通道故障',
}

export function alertTypeLabel(t: string): string {
  return ALERT_TYPE_LABELS[t] ?? t
}
