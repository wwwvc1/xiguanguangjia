/**
 * LLM 模型管理 API
 *
 * 端点(对应 backend/routers/admin_llm_models.py):
 *   GET    /api/admin/llm-models?owner=system|user|all&is_active=true|false
 *   POST   /api/admin/llm-models
 *   PUT    /api/admin/llm-models/{id}
 *   DELETE /api/admin/llm-models/{id}
 *   POST   /api/admin/llm-models/{id}/set-default
 *   POST   /api/admin/llm-models/{id}/test
 *
 * 端点(对应 backend/routers/admin_dashboard.py):
 *   GET    /api/admin/dashboard/llm-usage?days=7
 */
import http from './http'

// ────────────────────────── 类型 ──────────────────────────

/** LLM 模型(响应) */
export interface LLMModel {
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

/** 新建 LLM 模型 */
export interface LLMModelCreate {
  name: string
  base_url: string
  api_key: string
  model_name: string
  is_system_default?: boolean
  is_active?: boolean
  owner_user_id?: number | null
}

/** 更新 LLM 模型 */
export interface LLMModelUpdate {
  name?: string
  base_url?: string
  api_key?: string
  model_name?: string
  is_active?: boolean
}

/** 测活响应 */
export interface LLMTestResult {
  success: boolean
  latency_ms: number
  reply?: string | null
  error?: string | null
}

/** 用量每日桶 */
export interface LLMUsageBucket {
  date: string
  call_count: number
  user_count: number
}

/** 用量响应 */
export interface LLMUsageStats {
  days: number
  total_calls: number
  total_users: number
  daily: LLMUsageBucket[]
}

// ────────────────────────── CRUD ──────────────────────────

/** 列出模型 */
export function listModels(owner?: 'system' | 'user' | 'all', isActive?: boolean): Promise<LLMModel[]> {
  return http
    .get<LLMModel[]>('/admin/llm-models', {
      params: {
        ...(owner && owner !== 'all' ? { owner } : {}),
        ...(isActive !== undefined ? { is_active: isActive } : {})
      }
    })
    .then((r) => r.data)
}

/** 新建 */
export function createModel(payload: LLMModelCreate): Promise<LLMModel> {
  return http.post<LLMModel>('/admin/llm-models', payload).then((r) => r.data)
}

/** 更新 */
export function updateModel(id: number, patch: LLMModelUpdate): Promise<LLMModel> {
  return http.put<LLMModel>(`/admin/llm-models/${id}`, patch).then((r) => r.data)
}

/** 删除 */
export function deleteModel(id: number): Promise<{ message: string }> {
  return http.delete<{ message: string }>(`/admin/llm-models/${id}`).then((r) => r.data)
}

/** 设为系统默认 */
export function setDefaultModel(id: number): Promise<{ message: string; model_id: number }> {
  return http
    .post<{ message: string; model_id: number }>(`/admin/llm-models/${id}/set-default`)
    .then((r) => r.data)
}

/** 测活(单条 ping) */
export function testModel(id: number, prompt = '你好,请用一句话自我介绍。'): Promise<LLMTestResult> {
  return http
    .post<LLMTestResult>(`/admin/llm-models/${id}/test`, { prompt })
    .then((r) => r.data)
}

// ────────────────────────── 用量统计 ──────────────────────────

/** 7 日 / 30 日 / 90 日 LLM 用量折线 */
export function getLLMUsage(days = 7): Promise<LLMUsageStats> {
  return http
    .get<LLMUsageStats>('/admin/dashboard/llm-usage', { params: { days } })
    .then((r) => r.data)
}

export interface LLMTokenStats {
  days: number
  total: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
  by_model: {
    model: string
    calls: number
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    avg_tokens_per_call: number
  }[]
  by_day: { date: string; model: string; total_tokens: number }[]
}

export function getLLMTokenUsage(days = 30): Promise<LLMTokenStats> {
  return http
    .get<LLMTokenStats>('/admin/dashboard/llm-tokens', { params: { days } })
    .then((r) => r.data)
}
