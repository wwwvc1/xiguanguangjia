import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    /** 是否需要登录(默认 true,Login 显式 false) */
    requiresAuth?: boolean
    /** 路由标题,document.title 会拼到后面 */
    title?: string
    /** 是否仅 super_admin 可见 */
    requiresSuperAdmin?: boolean
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false, title: '登录' }
  },
  {
    path: '/',
    redirect: { name: 'Dashboard' }
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { requiresAuth: true, title: '仪表盘' }
  },
  {
    path: '/users',
    name: 'Users',
    component: () => import('@/views/UsersView.vue'),
    meta: { requiresAuth: true, title: '用户管理', requiresSuperAdmin: true }
  },
  {
    path: '/llm-models',
    name: 'LLMModels',
    component: () => import('@/views/LLMModelsView.vue'),
    meta: { requiresAuth: true, title: 'AI 模型', requiresSuperAdmin: true }
  },
  {
    path: '/knowledge',
    name: 'Knowledge',
    component: () => import('@/views/KnowledgeView.vue'),
    meta: { requiresAuth: true, title: '知识库', requiresSuperAdmin: true }
  },
  {
    path: '/achievements',
    name: 'Achievements',
    component: () => import('@/views/AchievementsView.vue'),
    meta: { requiresAuth: true, title: '成就管理' }
  },
  {
    path: '/logs',
    name: 'Logs',
    component: () => import('@/views/LogsView.vue'),
    meta: { requiresAuth: true, title: '系统日志', requiresSuperAdmin: true }
  },
  {
    path: '/announcements',
    name: 'Announcements',
    component: () => import('@/views/AnnouncementsView.vue'),
    meta: { requiresAuth: true, title: '公告' }
  },
  {
    path: '/insights',
    name: 'Insights',
    component: () => import('@/views/InsightsView.vue'),
    meta: { requiresAuth: true, title: '数据洞察' }
  },
  {
    path: '/data-asset/:type',
    name: 'DataAsset',
    component: () => import('@/views/DataAssetView.vue'),
    meta: { requiresAuth: true, title: '数据资产' }
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { requiresAuth: false, title: '404' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  }
})

// 路由守卫 — 未登录跳 Login;非 super_admin 访问 super_admin-only 路由跳 Dashboard
router.beforeEach((to) => {
  const auth = useAuthStore()
  const requiresAuth = to.meta.requiresAuth !== false

  if (requiresAuth && !auth.isLoggedIn) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }
  // 已登录访问 Login 自动跳 Dashboard
  if (to.name === 'Login' && auth.isLoggedIn) {
    return { name: 'Dashboard' }
  }
  // super_admin 路由守卫
  if (to.meta.requiresSuperAdmin && !auth.isSuperAdmin) {
    return { name: 'Dashboard' }
  }
  return true
})

router.afterEach((to) => {
  const base = '习惯管家 · 管理后台'
  document.title = to.meta.title ? `${to.meta.title} · ${base}` : base
})

export default router