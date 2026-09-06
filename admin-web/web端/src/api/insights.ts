/**
 * 数据洞察 + 数据资产 + AI 解读 API
 * 对应后端 routers/admin_insights.py + routers/admin_logs.py
 */
import http from './http'

// ─────────── 数据洞察(Web "数据洞察"页 4 张图) ───────────

export interface InsightOverview {
  total_users: number
  dau_7d: number
  active_rate_7d: number
  new_users_30d: number
  data_totals: Record<string, number>
}

export interface ScatterPoint {
  user_id: number
  username: string
  days: number
  completion: number
  total: number
  done: number
}

export interface TrendPoint { date: string; value: number }
export interface HourlyPoint { hour: number; value: number }
export interface HeatmapCell { dow: number; hour: number; value: number }

export const insightsApi = {
  overview: () => http.get<InsightOverview>('/admin/insights/overview').then((r) => r.data),
  scatter: (days = 30) => http.get<{ points: ScatterPoint[]; days: number }>('/admin/insights/scatter', { params: { days } }).then((r) => r.data),
  trend: (days = 30) => http.get<{ series: TrendPoint[]; days: number }>('/admin/insights/trend', { params: { days } }).then((r) => r.data),
  hourly: () => http.get<{ buckets: HourlyPoint[] }>('/admin/insights/hourly').then((r) => r.data),
  heatmap: () => http.get<{ cells: HeatmapCell[] }>('/admin/insights/heatmap').then((r) => r.data),
  /** 跑 AI 运营建议(系统默认模型) */
  aiSummary: () => http.post<{
    summary: InsightOverview
    ai_advice: string
  }>('/admin/insights/ai-summary/run').then((r) => r.data)
}

// ─────────── 数据资产下钻(7 个 type) ───────────

export type DataAssetType = 'todos' | 'goals' | 'transactions' | 'meals' | 'reminders' | 'achievements' | 'reports'

export interface DataAssetRow {
  id: number
  name?: string
  text?: string
  t?: string
  user_id: number
  username?: string | null
  nickname?: string | null
  amount?: number | null
  type?: string | null
  done?: number | null
  progress?: number | null
  status?: string | null
  code?: string | null
}

export const dataAssetApi = {
  list: (type: DataAssetType, page = 1, pageSize = 20, userId?: number) => {
    const params: Record<string, unknown> = { page, page_size: pageSize }
    if (userId) params.user_id = userId
    return http.get<{ type: string; total: number; page: number; page_size: number; rows: DataAssetRow[] }>(
      `/admin/insights/data-asset/${type}`, { params }
    ).then((r) => r.data)
  },
  aiAnalyze: (type: DataAssetType) => http.post<{ type: string; total: number; sample_size: number; ai_advice: string }>(
    `/admin/insights/data-asset/${type}/ai-analyze`
  ).then((r) => r.data)
}

// ─────────── 系统日志 AI 解读 ───────────

export const logAiApi = {
  preview: (limit = 50) => http.get<{
    limit: number
    by_action: { action: string; count: number; last_at: string }[]
    by_hour: { hour: number; value: number }[]
    recent_logs: { id: number; user_id: number; action: string; status: string; created_at: string }[]
  }>('/admin/logs/ai-summary/preview', { params: { limit } }).then((r) => r.data),
  run: (limit = 50) => http.post<{
    preview: any
    ai_insight: string
  }>('/admin/logs/ai-summary/run', null, { params: { limit } }).then((r) => r.data)
}
