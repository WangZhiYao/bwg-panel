export interface Sample {
  id: number; server_id: number; ts: string; status: string
  data_counter: number | null
  disk_used_b: number | null; disk_quota_b: number | null
  mem_available_kb: number | null; mem_total_kb: number | null
  swap_available_kb: number | null; swap_total_kb: number | null
  load_average: number | null; cpu_throttled: number | null
}

export interface ServerSummary {
  id: number; name: string; veid: string
  node_location: string | null; os: string | null; vm_type: string | null
  ip_addresses: string[]
  plan_disk: string | null; plan_ram: string | null; plan_swap: string | null
  traffic: { used: number | null; quota: number; next_reset: string | null }
  latest: Sample | null
  stale: boolean
}

export interface HistoryResult { samples: Sample[]; daily_usage: { date: string; bytes: number }[] }

export interface Meta {
  mock: boolean
  last_sample_at: number | null
  rate_limit: { remaining_points_15min: number; remaining_points_24h: number } | null
  version: string
}

export type HistoryRange = '24h' | '7d' | '30d'

export type PowerAction = 'start' | 'stop' | 'restart' | 'kill'

export interface Snapshot {
  fileName: string
  timestamp: number | null
  status: string | null
  description: string | null
  size: number | null
}

export type AlertType = 'offline' | 'traffic_warn' | 'traffic_critical' | 'cpu_throttle' | 'collect_error' | 'email_error'

export interface AlertRow {
  id: number
  server_id: number
  server_name: string
  type: AlertType
  message: string
  triggered_at: string
  resolved_at: string | null
  notified: boolean
  acknowledged: boolean
}

export interface PanelSettings {
  smtp_host: string
  smtp_port: number
  smtp_user: string
  smtp_from: string
  smtp_to: string[]
  threshold_warn: number
  threshold_critical: number
  sample_interval_seconds: number
  timezone: string
  smtp_pass_set: boolean  // 只读派生态：是否已存密码（密码本身永不回传）
}

export interface SettingsUpdate extends Partial<Omit<PanelSettings, 'smtp_to' | 'smtp_pass_set'>> {
  smtp_to?: string[]
  smtp_pass?: string
}
