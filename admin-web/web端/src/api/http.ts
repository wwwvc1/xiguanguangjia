import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import router from '@/router'
import type { useAuthStore } from '@/stores/auth'

/**
 * axios 单例
 *  - baseURL = '/api' 走 Vite proxy → 后端 8000
 *  - 请求拦截:加 Authorization Bearer
 *  - 响应拦截:401 → 清 token + 跳 Login
 *  - 错误:Phase 0 暂时 console.error,Phase 1+ 接 toast
 */

const http: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 20_000,
  headers: { 'Content-Type': 'application/json' }
})

// 安装请求/响应拦截器 — main.ts 里调用一次,注入 auth store
export function setupHttp(opts: { auth: ReturnType<typeof useAuthStore> }) {
  const { auth } = opts

  http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    if (auth.token) {
      config.headers.set('Authorization', `Bearer ${auth.token}`)
    }
    return config
  })

  http.interceptors.response.use(
    (resp) => resp,
    (err: AxiosError) => {
      const status = err.response?.status
      const url = err.config?.url ?? ''

      if (status === 401) {
        // 登录接口自身的 401 不弹错(交给 form)
        if (!url.includes('/admin/login')) {
          auth.logout()
          const redirect = router.currentRoute.value.fullPath
          router.replace({ name: 'Login', query: { redirect } })
        }
      } else if (status === 403) {
        // eslint-disable-next-line no-console
        console.warn('[http 403]', url)
      } else if (status && status >= 500) {
        // eslint-disable-next-line no-console
        console.error('[http 5xx]', status, url, err.message)
      }
      return Promise.reject(err)
    }
  )
}

export default http