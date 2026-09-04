/**
 * 仪表盘 KPI / 活动流 API (Phase 1.2)
 * 全部从后端真实拉数据,不再 throw 占位
 */
import http from './http'

// ────────────────────────── 后端响应模型 ──────────────────────────

/** /api/admin/stats 完整 schema(对应 backend DashboardStats) */
export interface DashboardStats {
  users: {
    total: number
    active_7d: number
    new_7d: number
    active_rate: number
  }
  data: {
    todos: number
    goals: number
    transactions: number
    meals: number
    reminders: number
    achievements: number
    reports: number
  }
  ai: {
    calls_7d: number
    calls_today: number
    unique_users_7d: number
  }
  llm: {
    models_total: number
    system_default_id: number | null
    system_default_name: string | null
  }
  knowledge: {
    documents: number
    chunks: number
  }
  logs_7d: number
}

/** /api/admin/dashboard/retention 单日桶 */
export interface RetentionBucket {
  date: string
  dau: number
  wau: number
  mau: number
}

export interface RetentionResponse {
  days: number
  buckets: RetentionBucket[]
  totals: {
    dau_avg: number
    wau_avg: number
    mau_avg: number
    peak_dau: number
  }
}

/** /api/admin/dashboard/llm-usage 单日桶 */
export interface LLMUsageBucket {
  date: string
  call_count: number
  user_count: number
}

export interface LLMUsageResponse {
  days: number
  total_calls: number
  total_users: number
  daily: LLMUsageBucket[]
}

/** /api/admin/auth/me */
export interface AdminMe {
  user_id: number
  username: string
  nickname: string | null
  avatar: string | null
  is_admin: boolean
  last_login_at: string | null
}

/** /api/admin/logs 单条 */
export interface AdminLogEntry {
  id: number
  user_id: number | null
  username: string | null
  action: string
  resource_type: string | null
  resource_id: number | null
  details: Record<string, unknown> | null
  ip: string | null
  user_agent: string | null
  status: 'success' | 'failed' | string
  created_at: string
}

export interface AdminLogListResp {
  total: number
  page: number
  page_size: number
  items: AdminLogEntry[]
}

/** /api/admin/llm-models 单条 */
export interface AdminLLMModel {
  id: number
  name: string
  base_url: string
  api_key: string
  model_name: string
  is_system_default: boolean
  is_active: boolean
  owner_user_id: number | null
  created_at: string
  updated_at: string
  api_key_masked: string
}

// ────────────────────────── 4 张 KPI 卡派生 ──────────────────────────

export interface DashboardKPI {
  key: 'users' | 'today_active' | 'ai_today' | 'online_admins'
  label: string
  value: number
  unit?: string
  delta_pct?: number
  trend?: 'up' | 'down' | 'flat'
  accent: 'blue' | 'green' | 'pink' | 'purple'
}

// ────────────────────────── 实现 ──────────────────────────

/** Dashboard 总览 */
export async function fetchStats(): Promise<DashboardStats> {
  const r = await http.get<DashboardStats>('/admin/stats')
  return r.data
}

/** 当前登录管理员信息 */
export async function fetchMe(): Promise<AdminMe> {
  const r = await http.get<AdminMe>('/admin/auth/me')
  return r.data
}

/** 最近 N 条操作日志(实时活动流用) */
export async function fetchRecentLogs(limit = 20): Promise<AdminLogEntry[]> {
  const r = await http.get<AdminLogListResp>('/admin/logs', {
    params: { page: 1, page_size: limit }
  })
  return r.data.items ?? []
}

/** DAU/WAU/MAU 折线 */
export async function fetchRetention(days = 30): Promise<RetentionResponse> {
  const r = await http.get<RetentionResponse>('/admin/dashboard/retention', {
    params: { days }
  })
  return r.data
}

/** LLM 用量按日聚合 */
export async function fetchLLMUsage(days = 7): Promise<LLMUsageResponse> {
  const r = await http.get<LLMUsageResponse>('/admin/dashboard/llm-usage', {
    params: { days }
  })
  return r.data
}

/** LLM 模型列表(测活统计用) */
export async function fetchLLMModels(): Promise<AdminLLMModel[]> {
  const r = await http.get<AdminLLMModel[]>('/admin/llm-models')
  return r.data
}

/** 测活单个 LLM(返回 success + latency_ms) */
export interface ModelTestResp {
  success: boolean
  latency_ms: number
  reply?: string | null
  error?: string | null
}
export async function testLLMModel(modelId: number): Promise<ModelTestResp> {
  const r = await http.post<ModelTestResp>(`/admin/llm-models/${modelId}/test`, {
    prompt: 'ping'
  })
  return r.data
}

// ────────────────────────── 派生 KPI ──────────────────────────

/** 从原始 stats 派生 4 张 KPI 卡 */
export function buildKPIs(stats: DashboardStats): DashboardKPI[] {
  const activeRate = (stats.users.active_rate ?? 0) * 100
  return [
    {
      key: 'users',
      label: '总用户',
      value: stats.users.total,
      delta_pct: stats.users.total > 0 ? activeRate : 0,
      trend: activeRate >= 50 ? 'up' : 'flat',
      accent: 'blue'
    },
    {
      key: 'today_active',
      label: '7 日活跃',
      value: stats.users.active_7d,
      delta_pct: activeRate,
      trend: activeRate >= 0 ? 'up' : 'flat',
      accent: 'purple'
    },
    {
      key: 'ai_today',
      label: '今日 AI 调用',
      value: stats.ai.calls_today,
      delta_pct: stats.ai.calls_7d > 0
        ? Math.round((stats.ai.calls_today / (stats.ai.calls_7d / 7)) * 100 - 100)
        : 0,
      trend: stats.ai.calls_today > 0 ? 'up' : 'flat',
      accent: 'green'
    },
    {
      key: 'online_admins',
      label: '在线管理员',
      value: 1, // 后端暂无 online admin 列表,固定 1(自己)
      delta_pct: 0,
      trend: 'flat',
      accent: 'pink'
    }
  ]
}
