/**
 * 用户管理 API
 * - list / detail / create / update / delete
 * - AI 对话列表 / 详情 / 单条删除 / 批量删除
 * - 重算成就 + 数据汇总
 */
import http from './http'
import type { Role } from '@/stores/auth'

// ─────────── 用户实体 ───────────

export interface UserDataCounts {
  todos?: number
  goals?: number
  transactions?: number
  meals?: number
  reminders?: number
  achievements?: number
  reports?: number
  [key: string]: number | undefined
}

/** /admin/users 列表项(对应后端 UserListItem) */
export interface UserItem {
  id: number
  username?: string | null
  nickname?: string | null
  avatar?: string | null
  openid?: string
  /** 后端 is_admin: true 表示管理员 */
  is_admin: boolean
  is_active: boolean
  /** 前端归一字段 — 由 is_admin + username 推出来 */
  role: Role
  email?: string | null
  created_at: string
  last_login_at?: string | null
  ai_calls_remaining: number
  data_counts: UserDataCounts
}

/** /admin/users/{id} 详情 */
export interface UserDetail extends UserItem {
  has_password?: boolean
}

/** 列表查询参数 */
export interface UserListQuery {
  page?: number
  page_size?: number
  keyword?: string
  is_active?: boolean
  is_admin?: boolean
}

export interface UserListResp {
  total: number
  page: number
  page_size: number
  items: UserItem[]
}

/** 新建用户 payload */
export interface NewUser {
  username: string
  password: string
  nickname?: string
  email?: string
  role: Role
  is_active?: boolean
}

/** 编辑用户 payload */
export interface UserPatch {
  nickname?: string
  email?: string
  role?: Role
  is_active?: boolean
}

/** /admin/users/{id}/data-summary */
export interface DataSummary {
  user_id: number
  data_counts: {
    todos: number
    goals: number
    transactions: number
    meals: number
    reminders: number
    achievements: number
    reports: number
    ai_chats_sessions: number
    ai_chats_messages: number
  }
  last_login_at?: string | null
  last_ai_chat_at?: string | null
}

/** /admin/users/{id}/ai-chats 单条 session */
export interface AIChatSession {
  session_id: string
  first_at?: string
  last_at?: string
  msg_count?: number
  first_user?: string
  model?: string | null
}

export interface AIChatsResponse {
  total: number
  items: AIChatSession[]
}

export interface AIChatMessage {
  id: number
  role: 'user' | 'assistant' | 'tool' | 'system' | string
  content: string
  tool_calls?: unknown
  model?: string | null
  created_at: string
}

export interface AIChatDetailResponse {
  session_id: string
  messages: AIChatMessage[]
}

export interface RecomputeAchievementsResp {
  user_id: number
  recomputed: number
  newly_unlocked: Array<{
      type: string
      name: string
      description?: string
      icon?: string
      current_value?: number
      target_value?: number
      metric_type?: string
      just_unlocked?: boolean
    }>
}

// ─────────── 工具:把后端 is_admin 归一到 Role ───────────

function roleOf(isAdmin: boolean | undefined): Role {
  return isAdmin ? 'super_admin' : 'viewer'
}

function normalizeUser<T extends { is_admin?: boolean; username?: string | null; email?: string | null }>(raw: T): T & { role: Role } {
  return { ...raw, email: raw.email ?? null, role: roleOf(raw.is_admin) } as T & { role: Role }
}

// ─────────── API 实现 ───────────

/** 用户列表 */
export async function listUsers(query: UserListQuery = {}): Promise<UserListResp> {
  const params: Record<string, unknown> = {
    page: query.page ?? 1,
    page_size: query.page_size ?? 20
  }
  if (query.keyword) params.q = query.keyword
  if (query.is_active !== undefined) params.is_active = query.is_active
  if (query.is_admin !== undefined) params.is_admin = query.is_admin

  const { data } = await http.get<UserListResp>('/admin/users', { params })
  return {
    ...data,
    items: (data.items ?? []).map((u) => normalizeUser(u))
  }
}

/** 用户详情 */
export async function getUser(id: number): Promise<UserDetail> {
  const { data } = await http.get<UserDetail>(`/admin/users/${id}`)
  return normalizeUser(data)
}

/** 创建用户 */
export async function createUser(payload: NewUser): Promise<UserDetail> {
  const { data } = await http.post<UserDetail>('/admin/users', {
    username: payload.username,
    password: payload.password,
    nickname: payload.nickname,
    email: payload.email,
    role: payload.role,
    is_active: payload.is_active ?? true
  })
  return normalizeUser(data)
}

/** 更新用户(部分字段) */
export async function updateUser(id: number, payload: UserPatch): Promise<UserDetail> {
  const body: Record<string, unknown> = {}
  if (payload.nickname !== undefined) body.nickname = payload.nickname
  if (payload.email !== undefined) body.email = payload.email
  if (payload.role !== undefined) body.role = payload.role
  if (payload.is_active !== undefined) body.is_active = payload.is_active
  const { data } = await http.patch<UserDetail>(`/admin/users/${id}`, body)
  return normalizeUser(data)
}

/** 删除用户(不能删自己 / 管理员) */
export async function deleteUser(id: number): Promise<{ message: string }> {
  const { data } = await http.delete<{ message: string }>(`/admin/users/${id}`)
  return data
}

/** 封禁/解禁 */
export async function setUserActive(id: number, isActive: boolean): Promise<{ message: string; is_active: boolean }> {
  const { data } = await http.patch<{ message: string; is_active: boolean }>(`/admin/users/${id}/active`, {
    is_active: isActive
  })
  return data
}

/** 重置密码 */
export async function resetUserPassword(id: number, newPassword: string): Promise<{ message: string }> {
  const { data } = await http.post<{ message: string }>(`/admin/users/${id}/reset-password`, {
    new_password: newPassword
  })
  return data
}

/** AI 对话 session 列表(分页) */
export async function getUserAIChats(
  id: number,
  params: { page?: number; page_size?: number } = {}
): Promise<AIChatsResponse> {
  const { data } = await http.get<AIChatsResponse>(`/admin/users/${id}/ai-chats`, {
    params: {
      page: params.page ?? 1,
      page_size: params.page_size ?? 30
    }
  })
  return data
}

/** 单 session 完整消息 */
export async function getUserAIChatDetail(userId: number, sessionId: string): Promise<AIChatDetailResponse> {
  const { data } = await http.get<AIChatDetailResponse>(
    `/admin/users/${userId}/ai-chats/${encodeURIComponent(sessionId)}`
  )
  return data
}

/** 删除单个 AI session */
export async function deleteAIChat(userId: number, sessionId: string): Promise<{ deleted: number; session_id: string }> {
  const { data } = await http.delete<{ deleted: number; session_id: string }>(
    `/admin/users/${userId}/ai-chats/${encodeURIComponent(sessionId)}`
  )
  return data
}

/** 批量删除某用户所有 AI 聊天记录 */
export async function deleteUserAIChats(userId: number, before?: string): Promise<{ deleted: number; before?: string | null }> {
  const { data } = await http.delete<{ deleted: number; before?: string | null }>(
    `/admin/users/${userId}/ai-chats`,
    { params: before ? { before } : {} }
  )
  return data
}

/** 重算某用户成就 */
export async function recomputeAchievements(userId: number): Promise<RecomputeAchievementsResp> {
  const { data } = await http.post<RecomputeAchievementsResp>(`/admin/users/${userId}/recompute-achievements`)
  return data
}

/** 用户数据汇总 */
export async function getUserDataSummary(id: number): Promise<DataSummary> {
  const { data } = await http.get<DataSummary>(`/admin/users/${id}/data-summary`)
  return data
}