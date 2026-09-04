<script setup lang="ts">
/**
 * GlassNav — 左侧导航栏 (Phase 1+ 接路由;Phase 0 显示路由清单 + 占位高亮)
 *
 * super_admin_only 项由 stores/ui.ts.isNavItemVisible 过滤
 */
import { computed } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { NAV_GROUPS } from '@/utils/constants'
import { useUIStore, isNavItemVisible, type NavItemMeta } from '@/stores/ui'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const ui = useUIStore()
const auth = useAuthStore()

const collapsed = computed(() => ui.leftNavCollapsed)

const currentName = computed(() => route.name?.toString() ?? '')

/** 按当前管理员角色过滤导航项 */
const visibleGroups = computed(() => {
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((it) => isNavItemVisible(it as NavItemMeta))
  })).filter((g) => g.items.length > 0)
})

const onLogout = () => {
  auth.logout()
  router.replace({ name: 'Login' })
}
</script>

<template>
  <aside class="glass-nav glass-2" :class="{ collapsed }">
    <div class="brand">
      <span class="brand-mark">◇</span>
      <span v-if="!collapsed" class="brand-name">习惯管家</span>
    </div>

    <nav class="nav-list">
      <template v-for="group in visibleGroups" :key="group.title">
        <div v-if="!collapsed" class="nav-title">{{ group.title }}</div>
        <RouterLink
          v-for="item in group.items"
          :key="item.name"
          :to="{ name: item.name }"
          class="nav-item"
          :class="{ active: currentName === item.name }"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span v-if="!collapsed" class="nav-label">{{ item.label }}</span>
        </RouterLink>
      </template>
    </nav>

    <div class="footer">
      <button class="nav-item ghost" @click="ui.toggleNav" :title="collapsed ? '展开' : '折叠'">
        <span class="nav-icon">{{ collapsed ? '»' : '«' }}</span>
        <span v-if="!collapsed">折叠</span>
      </button>
      <button class="nav-item ghost" @click="onLogout" title="退出登录">
        <span class="nav-icon">⎋</span>
        <span v-if="!collapsed">退出</span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.glass-nav {
  width: var(--nav-width);
  height: 100vh;
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  padding: 16px;
  gap: 8px;
  transition: width var(--t-med);
  flex-shrink: 0;
}
.glass-nav.collapsed { width: 64px; }

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px 16px;
  border-bottom: 1px solid var(--c-line);
  margin-bottom: 8px;
}
.brand-mark {
  width: 28px; height: 28px;
  display: grid; place-items: center;
  border-radius: 8px;
  background: var(--accent-gradient);
  color: #fff;
  font-weight: 700;
}
.brand-name {
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 600;
  color: var(--c-ink);
}

.nav-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}

.nav-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--c-ink-3);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 12px 12px 6px;
}
.nav-title:first-child { padding-top: 4px; }

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--r-sm);
  color: var(--c-ink-2);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  position: relative;
  transition: background var(--t-fast), color var(--t-fast);
  border: none;
  background: transparent;
  width: 100%;
  text-align: left;
}
.nav-item:hover {
  background: var(--glass-1-bg);
  color: var(--c-ink);
}
.nav-item.active {
  background: var(--glass-2-bg);
  color: var(--c-ink);
  box-shadow: inset 2px 0 0 var(--accent-1);
}
.nav-item.ghost {
  margin-top: auto;
  opacity: 0.7;
}
.nav-icon {
  width: 16px; height: 16px;
  display: grid; place-items: center;
  font-size: 14px;
}

.footer {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 8px;
  border-top: 1px solid var(--c-line);
}
</style>