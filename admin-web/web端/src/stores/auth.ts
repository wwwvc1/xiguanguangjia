import { defineStore } from 'pinia'
import http from '@/api/http'

/**
 * 管理员角色
 * - super_admin: 超级管理员(后端 /me 返回的过渡期 admin 也会落到这一档)
 * - admin:       旧版管理员,isSuperAdmin getter 一并视作
 * - viewer:      只读
 */
export type Role = 'super_admin' | 'admin' | 'operator' | 'viewer'

export interface AdminUser {
  id: number
  user_id?: number
  username: string
  display_name?: string
  nickname?: string
  email?: string
  role: Role
  is_admin?: boolean
  avatar?: string
  avatar_url?: string
  last_login_at?: string | null
}

interface AuthState {
  token: string
  user: AdminUser | null
}

const STORAGE_KEY = 'admin-auth'

function readPersisted(): Partial<AuthState> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function persist(state: AuthState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: state.token, user: state.user }))
  } catch {
    /* ignore quota / private mode */
  }
}

/** 把后端 role 字符串标准化为 Role(未知值兜底) */
function normalizeRole(raw: unknown, isAdmin?: boolean): Role {
  if (typeof raw === 'string') {
    const r = raw.toLowerCase()
    if (r === 'super_admin' || r === 'admin' || r === 'operator' || r === 'viewer') return r
  }
  return isAdmin ? 'super_admin' : 'viewer'
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    token: '',
    user: null
  }),

  getters: {
    isLoggedIn: (s) => Boolean(s.token),
    role: (s): Role | null => s.user?.role ?? null,
    /**
     * 超级管理员判定
     * - 过渡期:admin 与 super_admin 都视为 super_admin
     * - 后续 /me 完全返回 super_admin 后,可收紧为仅 super_admin
     */
    isSuperAdmin(): boolean {
      const r = this.user?.role
      return r === 'super_admin' || r === 'admin'
    },
    /** 用户管理权限(暂时所有 admin 都行) */
    canManageUsers(): boolean {
      return this.isSuperAdmin
    },
    displayName: (s) => s.user?.display_name ?? s.user?.nickname ?? s.user?.username ?? 'Admin'
  },

  actions: {
    /** main.ts 里调用一次,从 localStorage 恢复 */
    init() {
      const persisted = readPersisted()
      if (persisted.token) this.token = persisted.token
      if (persisted.user) this.user = persisted.user
    },

    /** Phase 1+ 接 /admin/auth/login(后端 admin_auth router) */
    async login(username: string, password: string): Promise<void> {
      const { data } = await http.post<{
        access_token?: string
        token?: string
        user?: AdminUser
        user_id?: number
        username?: string
        nickname?: string
        is_admin?: boolean
        role?: string
      }>('/admin/auth/login', { username, password })
      // 兼容两种后端字段命名
      const token = data.access_token || data.token || ''
      this.token = token
      this.user = data.user || {
        id: data.user_id ?? 0,
        user_id: data.user_id ?? 0,
        username: data.username ?? username,
        display_name: data.nickname ?? data.username ?? username,
        nickname: data.nickname,
        // 过渡期:登录后默认视为 super_admin,与 isSuperAdmin getter 一致
        role: normalizeRole(data.role, data.is_admin ?? true),
        is_admin: data.is_admin ?? true,
      }
      persist(this.$state)

      // 登录后立即拉一次 /me,把 role / nickname / avatar 全部拉齐
      try { await this.fetchMe() } catch { /* 失败不影响登录 */ }
    },

    logout() {
      this.token = ''
      this.user = null
      try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }
    },

    /** 拉取当前登录管理员信息,401 时 http 拦截器会自动 logout */
    async fetchMe(): Promise<AdminUser> {
      const { data } = await http.get<{
        user_id: number
        username: string
        nickname?: string | null
        avatar?: string | null
        is_admin: boolean
        role?: string
        last_login_at?: string | null
      }>('/admin/auth/me')

      // 后端返回 user_id,前端统一成 id
      const existing = this.user
      const merged: AdminUser = {
        id: data.user_id,
        user_id: data.user_id,
        username: data.username,
        display_name: data.nickname ?? existing?.display_name ?? data.username,
        nickname: data.nickname ?? existing?.nickname ?? undefined,
        role: normalizeRole(data.role, data.is_admin),
        is_admin: data.is_admin,
        avatar: data.avatar ?? existing?.avatar,
        avatar_url: data.avatar ?? existing?.avatar_url,
        last_login_at: data.last_login_at ?? null,
      }
      this.user = merged
      persist(this.$state)
      return merged
    }
  }
})