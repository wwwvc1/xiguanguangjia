<template>
  <a-layout class="admin-layout">
    <!-- 侧栏(桌面) -->
    <a-layout-sider
      v-if="!isMobile"
      :width="220"
      class="sider"
      theme="light"
    >
      <div class="logo">🏠 习惯管家</div>
      <a-menu
        :selected-keys="[route.name]"
        mode="inline"
        @click="onMenuClick"
      >
        <a-menu-item v-for="item in menuItems" :key="item.name">
          <component :is="item.icon" />
          <span>{{ item.meta.title }}</span>
        </a-menu-item>
      </a-menu>
    </a-layout-sider>

    <!-- 移动端顶栏 + 抽屉 -->
    <a-drawer
      v-if="isMobile"
      :open="drawerOpen"
      placement="left"
      :width="240"
      @close="drawerOpen = false"
    >
      <div class="logo">🏠 习惯管家</div>
      <a-menu :selected-keys="[route.name]" mode="inline" @click="onMobileMenuClick">
        <a-menu-item v-for="item in menuItems" :key="item.name">
          <component :is="item.icon" />
          <span>{{ item.meta.title }}</span>
        </a-menu-item>
      </a-menu>
    </a-drawer>

    <a-layout>
      <a-layout-header class="header">
        <a-button v-if="isMobile" type="text" @click="drawerOpen = true">
          <template #icon><MenuOutlined /></template>
        </a-button>
        <div class="header-right">
          <a-dropdown>
            <a-space>
              <a-avatar :size="32">{{ auth.user?.nickname?.[0] || 'A' }}</a-avatar>
              <span class="user-name">{{ auth.user?.nickname || auth.user?.username }}</span>
            </a-space>
            <template #overlay>
              <a-menu>
                <a-menu-item @click="onLogout">退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>

      <a-layout-content class="content">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  DashboardOutlined, TeamOutlined, RobotOutlined, BookOutlined,
  FileTextOutlined, TrophyOutlined, MenuOutlined
} from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { adminLogout as apiLogout } from '@/api/admin'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const isMobile = ref(window.innerWidth < 768)
const drawerOpen = ref(false)

const handleResize = () => { isMobile.value = window.innerWidth < 768 }
onMounted(() => window.addEventListener('resize', handleResize))
onUnmounted(() => window.removeEventListener('resize', handleResize))

const menuItems = computed(() => {
  return router.options.routes
    .find(r => r.path === '/')?.children
    .filter(c => c.meta?.title)
    .map(c => ({ ...c, icon: iconMap[c.name] }))
    .filter(c => c.icon)
})

const iconMap = {
  Dashboard: DashboardOutlined,
  Users: TeamOutlined,
  LLMModels: RobotOutlined,
  Knowledge: BookOutlined,
  Logs: FileTextOutlined,
  Achievements: TrophyOutlined
}

const onMenuClick = ({ key }) => router.push({ name: key })
const onMobileMenuClick = ({ key }) => {
  router.push({ name: key })
  drawerOpen.value = false
}

const onLogout = async () => {
  try { await apiLogout() } catch (e) {}
  auth.logout()
  message.success('已退出')
  router.push('/login')
}
</script>

<style scoped>
.admin-layout { min-height: 100vh; }
.sider { box-shadow: 2px 0 8px rgba(0,0,0,0.04); }
.logo {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 600;
  color: #5A6573;
  border-bottom: 1px solid #f0f0f0;
}
.header {
  background: #fff;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.header-right { display: flex; align-items: center; gap: 12px; }
.user-name { color: #5A6573; font-weight: 500; }
.content {
  padding: 24px;
  background: #F5F5F5;
  min-height: calc(100vh - 64px);
}
@media (max-width: 768px) {
  .content { padding: 16px; }
}
</style>
