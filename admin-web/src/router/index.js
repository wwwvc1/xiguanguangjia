// 路由 + 守卫
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true }
  },
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '仪表盘', icon: 'dashboard' }
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/users/UsersView.vue'),
        meta: { title: '用户管理', icon: 'team' }
      },
      {
        path: 'llm-models',
        name: 'LLMModels',
        component: () => import('@/views/llm-models/LLMModelsView.vue'),
        meta: { title: 'AI 模型', icon: 'robot' }
      },
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('@/views/knowledge/KnowledgeView.vue'),
        meta: { title: '知识库', icon: 'book' }
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('@/views/logs/LogsView.vue'),
        meta: { title: '系统日志', icon: 'file-text' }
      },
      {
        path: 'achievements',
        name: 'Achievements',
        component: () => import('@/views/achievements/AchievementsView.vue'),
        meta: { title: '成就定义', icon: 'trophy' }
      }
    ]
  },
  { path: '/:pathMatch(.*)*', component: () => import('@/views/NotFoundView.vue') }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    return next()
  }
  if (!auth.token) {
    return next('/login')
  }
  // 有 token 但没 user 信息,fetch 一下
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch (e) {
      return next('/login')
    }
  }
  next()
})

export default router
