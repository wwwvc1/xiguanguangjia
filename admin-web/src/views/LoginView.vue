<template>
  <div class="login-page">
    <a-card class="login-card">
      <div class="login-header">
        <div class="logo">🏠</div>
        <h2>习惯管家 管理后台</h2>
        <p class="hint">请使用管理员账号登录</p>
      </div>
      <a-form :model="form" :rules="rules" ref="formRef" @finish="onSubmit" layout="vertical">
        <a-form-item label="用户名" name="username">
          <a-input v-model:value="form.username" placeholder="请输入用户名" size="large" prefix="👤" />
        </a-form-item>
        <a-form-item label="密码" name="password">
          <a-input-password v-model:value="form.password" placeholder="请输入密码" size="large" prefix="🔒" />
        </a-form-item>
        <a-button type="primary" html-type="submit" :loading="loading" block size="large">
          登录
        </a-button>
      </a-form>
    </a-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const formRef = ref()

const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名' }],
  password: [{ required: true, min: 6, message: '密码至少 6 位' }]
}

const onSubmit = async () => {
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    message.success('登录成功')
    router.push('/')
  } catch (e) {
    // 错误已由 http 拦截器处理
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #E8E4E0 0%, #C8D5D9 100%);
  padding: 16px;
}
.login-card {
  width: 100%;
  max-width: 420px;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.08);
}
.login-header {
  text-align: center;
  margin-bottom: 24px;
}
.logo {
  font-size: 56px;
  margin-bottom: 8px;
}
.login-header h2 {
  margin: 0 0 4px 0;
  color: #5A6573;
}
.hint {
  color: #999;
  margin: 0;
  font-size: 14px;
}
</style>
