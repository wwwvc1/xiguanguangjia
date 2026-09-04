import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { setupHttp } from './api/http'
import { useAuthStore } from './stores/auth'
import { useThemeStore } from './stores/theme'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)

// 主题 + 鉴权 store 必须在 router 之前初始化
// (router.beforeEach 里需要读取 token)
useThemeStore().init()

const auth = useAuthStore()
auth.init()

setupHttp({ auth })

app.use(router)

// 全局错误处理 — Phase 1+ 接 toast
app.config.errorHandler = (err, instance, info) => {
  // eslint-disable-next-line no-console
  console.error('[Vue error]', { err, info, instance })
}

app.mount('#app')