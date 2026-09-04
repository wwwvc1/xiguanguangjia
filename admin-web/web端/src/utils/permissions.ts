/**
 * 权限矩阵 — 与 stores/auth.ts 的 Role 对齐
 * Phase 0: 仅类型 + 占位函数;Phase 1+ 接入路由级别 meta.requiresPermission
 */
import type { Role } from '@/stores/auth'

export type Permission =
  | 'user.read'
  | 'user.write'
  | 'model.read'
  | 'model.write'
  | 'knowledge.read'
  | 'knowledge.write'
  | 'achievement.read'
  | 'achievement.write'
  | 'log.read'
  | 'log.export'
  | 'announcement.read'
  | 'announcement.write'
  | 'insight.read'
  | 'insight.generate'

const MATRIX: Record<Role, Permission[]> = {
  super_admin: [
    'user.read', 'user.write',
    'model.read', 'model.write',
    'knowledge.read', 'knowledge.write',
    'achievement.read', 'achievement.write',
    'log.read', 'log.export',
    'announcement.read', 'announcement.write',
    'insight.read', 'insight.generate'
  ],
  admin: [
    'user.read', 'user.write',
    'model.read', 'model.write',
    'knowledge.read', 'knowledge.write',
    'achievement.read', 'achievement.write',
    'log.read', 'log.export',
    'announcement.read', 'announcement.write',
    'insight.read', 'insight.generate'
  ],
  operator: [
    'user.read',
    'model.read',
    'knowledge.read',
    'achievement.read', 'achievement.write',
    'log.read',
    'announcement.read', 'announcement.write',
    'insight.read'
  ],
  viewer: [
    'user.read',
    'model.read',
    'knowledge.read',
    'achievement.read',
    'log.read',
    'announcement.read',
    'insight.read'
  ]
}

export function can(role: Role | null | undefined, perm: Permission): boolean {
  if (!role) return false
  return MATRIX[role].includes(perm)
}

export function canAny(role: Role | null | undefined, perms: Permission[]): boolean {
  return perms.some((p) => can(role, p))
}