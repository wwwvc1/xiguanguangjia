<script setup lang="ts">
/**
 * LoginView — 登录页
 * 接后端 /admin/auth/login(Phase 1+),失败显示错误
 */
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import GlassInput from '@/components/form/GlassInput.vue'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const username = ref('admin')
const password = ref('Admin@123')
const submitting = ref(false)
const err = ref('')

const onSubmit = async () => {
  err.value = ''
  if (!username.value || !password.value) {
    err.value = '请输入账号和密码'
    return
  }
  submitting.value = true
  try {
    await auth.login(username.value, password.value)
    const redirect = (route.query.redirect as string) || '/dashboard'
    router.replace(redirect)
  } catch (e: any) {
    submitting.value = false
    const status = e?.response?.status
    const detail = e?.response?.data?.detail
    err.value = status === 401
      ? (detail || '账号或密码错误')
      : (detail || e?.message || '登录失败,请检查后端是否启动')
  }
}
</script>

<template>
  <main class="login-page">
    <div class="card glass-2">
      <div class="brand">
        <span class="mark">◇</span>
        <h1 class="serif">习惯管家</h1>
        <p class="sub">运营管理后台</p>
      </div>

      <form class="form" @submit.prevent="onSubmit">
        <div class="field">
          <label>账号</label>
          <GlassInput v-model="username" placeholder="请输入账号" />
        </div>
        <div class="field">
          <label>密码</label>
          <GlassInput v-model="password" type="password" placeholder="请输入密码" />
        </div>

        <button class="btn-primary" :disabled="submitting" type="submit">
          {{ submitting ? '登录中…' : '登录' }}
        </button>

        <div v-if="err" class="err">{{ err }}</div>
      </form>

      <div class="meta">
        <span>默认 admin / Admin@123 · 后端需跑在 :8000</span>
      </div>
    </div>
  </main>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid; place-items: center;
  padding: 24px;
  position: relative;
}
.login-page::before {
  content: '';
  position: absolute; inset: 0;
  background-image: radial-gradient(circle, var(--c-ink) 1px, transparent 1px);
  background-size: 24px 24px;
  opacity: 0.03;
  pointer-events: none;
}
.card {
  width: 100%; max-width: 420px;
  padding: 36px 32px;
  border-radius: var(--r-lg);
  position: relative;
  overflow: hidden;
}
.card::before {
  content: '';
  position: absolute; inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: var(--accent-gradient);
  -webkit-mask:
    linear-gradient(#fff 0 0) content-box,
    linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}
.brand {
  display: flex; flex-direction: column; align-items: center;
  margin-bottom: 28px;
  text-align: center;
}
.mark {
  width: 48px; height: 48px;
  border-radius: 14px;
  background: var(--accent-gradient);
  color: #fff;
  font-size: 24px; font-weight: 700;
  display: grid; place-items: center;
  margin-bottom: 16px;
  box-shadow: var(--accent-glow);
}
.brand h1 {
  font-size: 26px; font-weight: 700; color: var(--c-ink);
  margin-bottom: 4px;
}
.sub { font-size: 13px; color: var(--c-ink-3); letter-spacing: 0.04em; }

.field { margin-bottom: 16px; }
.field label {
  display: block;
  font-size: 12px; font-weight: 600;
  color: var(--c-ink-2);
  margin-bottom: 6px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.btn-primary {
  width: 100%;
  padding: 14px;
  margin-top: 8px;
  border: none;
  border-radius: var(--r-sm);
  background: var(--accent-gradient);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: transform var(--t-fast), box-shadow var(--t-fast);
  box-shadow: 0 4px 16px rgba(124, 92, 255, 0.35);
}
.btn-primary:hover { transform: translateY(-1px); box-shadow: 0 8px 24px rgba(124, 92, 255, 0.45); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }

.err {
  margin-top: 12px;
  font-size: 12px; color: var(--state-warning);
  background: rgba(234, 179, 8, 0.10);
  padding: 8px 12px;
  border-radius: var(--r-sm);
}

.meta {
  margin-top: 20px;
  font-size: 11px;
  color: var(--c-ink-3);
  text-align: center;
}
</style>