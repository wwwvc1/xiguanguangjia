import { defineStore } from 'pinia'
import { useAuthStore } from './auth'
import type { Role } from './auth'

const STORAGE_KEY = 'admin-ui'

interface UIState {
  leftNavCollapsed: boolean
  rightSidebarVisible: boolean
}

function readPersisted(): Partial<UIState> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function persist(state: UIState) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)) } catch { /* ignore */ }
}

export const useUIStore = defineStore('ui', {
  state: (): UIState => ({
    leftNavCollapsed: false,
    rightSidebarVisible: true,
    ...readPersisted()
  }),

  actions: {
    toggleNav() {
      this.leftNavCollapsed = !this.leftNavCollapsed
      persist(this.$state)
    },
    toggleSidebar() {
      this.rightSidebarVisible = !this.rightSidebarVisible
      persist(this.$state)
    },
    setRightSidebar(v: boolean) {
      this.rightSidebarVisible = v
      persist(this.$state)
    }
  }
})

/**
 * 角色工具
 *  - 当前所有登录管理员都被视为 super_admin(过渡期)
 *  - 后续 /me 完整返回 role 后,可在此收紧判定
 */

/** 当前登录管理员角色(可能为 null) */
export function currentRole(): Role | null {
  return useAuthStore().role
}

/** 是否超级管理员(用于菜单可见性 / 路由权限) */
export function isSuperAdminNow(): boolean {
  return useAuthStore().isSuperAdmin
}

/**
 * 导航项可见性
 *  - 默认全部可见
 *  - 标记 super_admin_only 的项:仅 super_admin 可见
 */
export interface NavItemMeta {
  name: string
  label: string
  icon: string
  super_admin_only?: boolean
}

export function isNavItemVisible(item: NavItemMeta): boolean {
  if (!item.super_admin_only) return true
  return isSuperAdminNow()
}