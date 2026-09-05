/**
 * 系统日志 API
 * - 对应后端 backend/routers/admin_logs.py
 * - 端点:/api/admin/logs/*  (受 admin token 保护)
 */
import http from './http'

// ─────────── 类型(对齐后端 OperationLogResponse) ───────────

export interface LogEntry {
  id: number
  user_id: number | null
  username: string | null
  action: string                  // 如 'upload_knowledge_doc'
  resource_type: string | null    // 如 'knowledge_document'
  resource_id: number | null
  details: Record<string, unknown> | null
  ip: string | null
  user_agent: string | null
  status: 'success' | 'failed' | string
  created_at: string              // ISO datetime
}

export interface LogListQuery {
  user_id?: number
  action?: string
  status?: 'success' | 'failed'
  date_from?: string              // YYYY-MM-DD
  date_to?: string
  page?: number
  page_size?: number
}

export interface LogListResp {
  total: number
  page: number
  page_size: number
  items: LogEntry[]
}

export interface LogActionsResp {
  actions: string[]
}

// ─────────── API ───────────

/** 日志列表(分页 + 过滤) */
export function listLogs(query: LogListQuery = {}): Promise<LogListResp> {
  const params: Record<string, unknown> = {}
  if (query.user_id !== undefined) params.user_id = query.user_id
  if (query.action !== undefined && query.action) params.action = query.action
  if (query.status) params.status = query.status
  if (query.date_from) params.date_from = query.date_from
  if (query.date_to) params.date_to = query.date_to
  if (query.page) params.page = query.page
  if (query.page_size) params.page_size = query.page_size
  return http.get<LogListResp>('/admin/logs', { params }).then((r) => r.data)
}

/** 所有出现过的 action 类型(给下拉筛选) */
export function listLogActions(): Promise<LogActionsResp> {
  return http.get<LogActionsResp>('/admin/logs/actions').then((r) => r.data)
}

/** 导出 CSV(直接返回 blob) */
export function exportLogs(query: LogListQuery = {}): Promise<Blob> {
  const params: Record<string, unknown> = {}
  if (query.user_id !== undefined) params.user_id = query.user_id
  if (query.action !== undefined && query.action) params.action = query.action
  if (query.date_from) params.date_from = query.date_from
  if (query.date_to) params.date_to = query.date_to
  return http
    .get('/admin/logs/export', { params, responseType: 'blob' })
    .then((r) => r.data as Blob)
}
