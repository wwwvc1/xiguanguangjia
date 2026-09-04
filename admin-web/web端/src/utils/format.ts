/**
 * 格式化工具 — Phase 0 占位实现,Phase 1+ 按需增强
 */

export function formatNumber(n: number | null | undefined, opts: { decimals?: number } = {}): string {
  if (n == null || Number.isNaN(n)) return '—'
  const { decimals = 0 } = opts
  return n.toLocaleString('zh-CN', { maximumFractionDigits: decimals, minimumFractionDigits: decimals })
}

export function formatPercent(p: number | null | undefined, decimals = 1): string {
  if (p == null || Number.isNaN(p)) return '—'
  const sign = p > 0 ? '+' : ''
  return `${sign}${(p * 100).toFixed(decimals)}%`
}

export function formatDate(ts: string | number | Date, withTime = false): string {
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return '—'
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  if (!withTime) return `${y}-${m}-${day}`
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day} ${hh}:${mm}`
}

export function formatRelativeTime(ts: string | number | Date): string {
  const d = new Date(ts).getTime()
  if (Number.isNaN(d)) return '—'
  const diff = Date.now() - d
  const s = Math.round(diff / 1000)
  if (s < 60) return `${s} 秒前`
  const m = Math.round(s / 60)
  if (m < 60) return `${m} 分钟前`
  const h = Math.round(m / 60)
  if (h < 24) return `${h} 小时前`
  const day = Math.round(h / 24)
  if (day < 30) return `${day} 天前`
  return formatDate(d)
}

export function formatBytes(bytes: number, decimals = 1): string {
  if (!bytes) return '0 B'
  const k = 1024
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(decimals)} ${units[i]}`
}

export function truncate(s: string, max = 80): string {
  if (!s) return ''
  return s.length > max ? `${s.slice(0, max)}…` : s
}