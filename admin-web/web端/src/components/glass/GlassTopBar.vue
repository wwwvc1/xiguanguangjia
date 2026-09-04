<script setup lang="ts">
/**
 * GlassTopBar — 顶部条 (面包屑 + 主题切换 + 用户菜单占位)
 */
import { useRoute, useRouter } from 'vue-router'
import { useThemeStore } from '@/stores/theme'
import { useAuthStore } from '@/stores/auth'

interface Props {
  title?: string
}
const props = defineProps<Props>()

const route = useRoute()
const router = useRouter()
const theme = useThemeStore()
const auth = useAuthStore()

const themeIcon = () => {
  if (theme.mode === 'auto') return '◑'
  return theme.resolved === 'dark' ? '☾' : '☼'
}
const nextThemeLabel = () => {
  if (theme.mode === 'auto') return '自动'
  return theme.resolved === 'dark' ? '暗' : '亮'
}

const onLogout = () => {
  auth.logout()
  router.replace({ name: 'Login' })
}
</script>

<template>
  <header class="glass-topbar glass-1">
    <div class="left">
      <div class="crumb">
        <span class="crumb-section">运营</span>
        <span class="crumb-sep">/</span>
        <span class="crumb-current">{{ props.title || (route.meta.title as string) || '' }}</span>
      </div>
    </div>

    <div class="right">
      <button class="icon-btn" :title="`主题: ${nextThemeLabel()}`" @click="theme.toggle">
        <span class="ic">{{ themeIcon() }}</span>
      </button>
      <button class="icon-btn" title="搜索">⌕</button>
      <button class="icon-btn" title="通知">
        <span>◔</span>
        <span class="dot" />
      </button>

      <div class="user-chip">
        <span class="avatar">{{ auth.displayName.slice(0, 1) }}</span>
        <span class="name">{{ auth.displayName }}</span>
        <button class="logout" @click="onLogout" title="退出">⎋</button>
      </div>
    </div>
  </header>
</template>

<style scoped>
.glass-topbar {
  height: var(--topbar-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 30;
}
.left { display: flex; align-items: center; gap: 12px; }
.right { display: flex; align-items: center; gap: 10px; }

.crumb {
  display: flex; align-items: center; gap: 10px;
  font-size: 13px; color: var(--c-ink-2);
}
.crumb-section { color: var(--c-ink-3); }
.crumb-sep { color: var(--c-ink-3); opacity: 0.6; }
.crumb-current { color: var(--c-ink); font-weight: 600; }

.icon-btn {
  position: relative;
  width: 36px; height: 36px;
  display: grid; place-items: center;
  border-radius: var(--r-sm);
  background: transparent;
  border: none;
  color: var(--c-ink-2);
  font-size: 16px;
  transition: background var(--t-fast), color var(--t-fast);
}
.icon-btn:hover {
  background: var(--glass-1-bg);
  color: var(--c-ink);
}
.dot {
  position: absolute; top: 9px; right: 9px;
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent-1);
}

.user-chip {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 10px 4px 4px;
  border-radius: var(--r-pill);
  background: var(--glass-2-bg);
  border: 1px solid var(--c-line);
  margin-left: 6px;
}
.avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--accent-gradient);
  color: #fff;
  display: grid; place-items: center;
  font-size: 12px; font-weight: 600;
}
.name { font-size: 13px; font-weight: 500; color: var(--c-ink); }
.logout {
  border: none; background: transparent;
  color: var(--c-ink-3); font-size: 14px;
  width: 24px; height: 24px; border-radius: 50%;
  transition: background var(--t-fast), color var(--t-fast);
}
.logout:hover { background: var(--glass-1-bg); color: var(--c-ink); }

@media (max-width: 768px) {
  .name { display: none; }
  .crumb-section { display: none; }
}
</style>