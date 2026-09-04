/**
 * 全局常量 — Phase 0 占位
 */

export const APP_NAME = '习惯管家 · 管理后台'
export const APP_VERSION = '0.1.0-phase0'

export const PAGINATION = {
  defaultPage: 1,
  defaultPageSize: 20,
  pageSizes: [10, 20, 50, 100] as const
}

export const DATE_RANGE_OPTIONS = [
  { label: '今日', value: 'today' },
  { label: '近 7 天', value: '7d' },
  { label: '近 30 天', value: '30d' },
  { label: '近 90 天', value: '90d' }
] as const

/**
 * 导航分组
 *  - super_admin_only: 仅 super_admin 可见(过渡期所有 admin 都是 super_admin,不实际生效)
 */
export const NAV_GROUPS = [
  {
    title: '总览',
    items: [
      { name: 'Dashboard', label: '仪表盘', icon: '⊞' }
    ]
  },
  {
    title: '运营',
    items: [
      { name: 'Users', label: '用户管理', icon: '☉', super_admin_only: true },
      { name: 'Achievements', label: '成就管理', icon: '★' },
      { name: 'Announcements', label: '公告', icon: '◐' }
    ]
  },
  {
    title: 'AI',
    items: [
      { name: 'LLMModels', label: 'AI 模型', icon: '◈', super_admin_only: true },
      { name: 'Knowledge', label: '知识库', icon: '◊', super_admin_only: true },
      { name: 'Insights', label: '数据洞察', icon: '⌬' }
    ]
  },
  {
    title: '系统',
    items: [
      { name: 'Logs', label: '系统日志', icon: '⌖', super_admin_only: true }
    ]
  }
] as const