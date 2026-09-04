/**
 * 成就管理 API
 *
 * 端点(对应 backend/routers/admin_achievements.py):
 *   GET    /api/admin/achievements/
 *   GET    /api/admin/achievements/{id}
 *   POST   /api/admin/achievements/
 *   PUT    /api/admin/achievements/{id}
 *   DELETE /api/admin/achievements/{id}
 *   GET    /api/admin/achievements/metrics
 *
 * 端点(本批次新增,需后端配合):
 *   GET    /api/admin/achievements/stats
 *   POST   /api/admin/achievements/users/{user_id}/recompute
 *   POST   /api/admin/achievements/try-metric
 */
import http from './http'

// ────────────────────────── 类型 ──────────────────────────

/** 成就定义(响应) */
export interface Achievement {
  id: number
  code: string
  name: string
  description: string | null
  icon: string
  metric_type: string
  target_value: number
  is_active: boolean
  sort_order: number
  created_at?: string
}

/** metric_type 元数据 */
export interface MetricType {
  value: string
  label: string
  unit: string
  desc: string
}

/** 列表响应 */
export interface AchievementListResp {
  items: Achievement[]
  total: number
}

/** metric 元数据响应 */
export interface MetricListResp {
  metrics: MetricType[]
}

/** 创建 */
export interface AchievementCreate {
  code: string
  name: string
  description?: string | null
  icon?: string
  metric_type: string
  target_value?: number
  is_active?: number | boolean
  sort_order?: number
}

/** 更新 */
export interface AchievementUpdate {
  name?: string
  description?: string | null
  icon?: string
  metric_type?: string
  target_value?: number
  is_active?: number | boolean
  sort_order?: number
}

/** 统计行(per-achievement 解锁情况) */
export interface AchievementStatRow {
  id: number
  code: string
  name: string
  icon: string
  metric_type: string
  target_value: number
  is_active: boolean
  unlock_count: number
  total_users: number
  unlock_rate: number  // 0-1
}

/** 统计总览 */
export interface AchievementStats {
  total_definitions: number
  active_definitions: number
  total_users: number
  total_unlocks: number
  rows: AchievementStatRow[]
}

/** 试用 metric 输入 */
export interface TryMetricReq {
  user_id: number
  metric_type: string
  target_value?: number
}

/** 试用 metric 输出 */
export interface TryMetricResult {
  user_id: number
  metric_type: string
  current_value: number
  target_value: number
  reached: boolean
  progress: number  // 0-1
  unit: string
}

/** 重新计算响应 */
export interface RecomputeResp {
  user_id: number
  newly_unlocked: Array<{
    type: string
    name: string
    description: string
    icon: string
    current_value: number
    target_value: number
  }>
  count: number
}

// ────────────────────────── CRUD ──────────────────────────

export function listAchievements(): Promise<Achievement[]> {
  return http.get<AchievementListResp>('/admin/achievements/').then((r) => r.data.items ?? [])
}

export function getAchievement(id: number): Promise<Achievement> {
  return http.get<Achievement>(`/admin/achievements/${id}`).then((r) => r.data)
}

export function createAchievement(payload: AchievementCreate): Promise<Achievement> {
  return http.post<Achievement>('/admin/achievements/', payload).then((r) => r.data)
}

export function updateAchievement(id: number, patch: AchievementUpdate): Promise<Achievement> {
  return http.put<Achievement>(`/admin/achievements/${id}`, patch).then((r) => r.data)
}

export function deleteAchievement(id: number): Promise<{ ok: boolean; deleted_id: number }> {
  return http.delete<{ ok: boolean; deleted_id: number }>(`/admin/achievements/${id}`).then((r) => r.data)
}

export function getMetricTypes(): Promise<MetricType[]> {
  return http.get<MetricListResp>('/admin/achievements/metrics').then((r) => r.data.metrics ?? [])
}

// ────────────────────────── 统计 / 试用 / 重算 ──────────────────────────

/** 全部成就的解锁统计(per-achievement + total_users) */
export function getAchievementStats(): Promise<AchievementStats> {
  return http.get<AchievementStats>('/admin/achievements/stats').then((r) => r.data)
}

/** 试用某 metric — 看指定 user 的当前值 / 目标 / 达成率 */
export function tryMetric(req: TryMetricReq): Promise<TryMetricResult> {
  return http.post<TryMetricResult>('/admin/achievements/try-metric', req).then((r) => r.data)
}

/** 对指定 user 强制重新评估并解锁 */
export function recomputeUserAchievements(userId: number): Promise<RecomputeResp> {
  return http
    .post<RecomputeResp>(`/admin/achievements/users/${userId}/recompute`)
    .then((r) => r.data)
}
