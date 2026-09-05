<script setup lang="ts">
/**
 * GlassTopBar — 顶部条 (面包屑 + 主题切换 + 弹窗设置 + 用户菜单)
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'
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

// 弹窗设置面板
const showSettings = ref(false)
const settingsRef = ref<HTMLElement | null>(null)
function toggleSettings() { showSettings.value = !showSettings.value }
function closeSettings() { showSettings.value = false }
function onClickOutside(e: MouseEvent) {
  if (!showSettings.value) return
  if (settingsRef.value && !settingsRef.value.contains(e.target as Node)) {
    showSettings.value = false
  }
}
onMounted(() => document.addEventListener('mousedown', onClickOutside))
onBeforeUnmount(() => document.removeEventListener('mousedown', onClickOutside))
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

      <!-- 弹窗设置 -->
      <div ref="settingsRef" class="settings-wrap">
        <button class="icon-btn" :title="'弹窗透明度 / 颜色'" @click="toggleSettings">
          <span class="ic">⚙</span>
        </button>
        <div v-if="showSettings" class="settings-popover">
          <div class="set-title">弹窗外观</div>

          <div class="set-row">
            <label>不透明度</label>
            <input
              type="range" min="0.4" max="1" step="0.02"
              :value="theme.modal.opacity"
              @input="(e) => theme.setModal({ opacity: Number((e.target as HTMLInputElement).value) })"
            />
            <span class="set-val">{{ Math.round(theme.modal.opacity * 100) }}%</span>
          </div>

          <div class="set-row">
            <label>蒙层</label>
            <input
              type="range" min="0" max="0.9" step="0.05"
              :value="theme.modal.maskOpacity"
              @input="(e) => theme.setModal({ maskOpacity: Number((e.target as HTMLInputElement).value) })"
            />
            <span class="set-val">{{ Math.round(theme.modal.maskOpacity * 100) }}%</span>
          </div>

          <div class="set-row">
            <label>主题色</label>
            <div class="tint-row">
              <button
                v-for="c in [null, '#7c5cff', '#142a20', '#8E3D2A', '#D8C9A5', '#1f6feb']"
                :key="c ?? 'auto'"
                class="tint-swatch"
                :class="{ active: theme.modal.tint === c }"
                :style="c ? { background: c } : { background: 'linear-gradient(135deg, #fff, #142a20)' }"
                :title="c ?? '跟随主题'"
                @click="theme.setModal({ tint: c })"
              />
            </div>
          </div>

          <button class="set-reset" @click="theme.resetModal">恢复默认</button>
        </div>
      </div>

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

/* 弹窗设置 popover */
.settings-wrap { position: relative; }
.settings-popover {
  position: absolute; top: calc(100% + 8px); right: 0;
  width: 280px;
  background: var(--c-paper, #fff);
  border: 1px solid var(--c-line);
  border-radius: var(--r-md);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
  padding: 14px 16px;
  display: flex; flex-direction: column; gap: 12px;
  z-index: 200;
}
.set-title {
  font-size: 12px; font-weight: 600;
  color: var(--c-ink); letter-spacing: 0.04em;
  text-transform: uppercase;
  padding-bottom: 4px; border-bottom: 1px solid var(--c-line);
}
.set-row {
  display: flex; align-items: center; gap: 10px;
  font-size: 12px; color: var(--c-ink-2);
}
.set-row label { width: 56px; flex-shrink: 0; }
.set-row input[type="range"] {
  flex: 1; min-width: 0; accent-color: var(--accent-1);
}
.set-val {
  font-family: var(--font-mono);
  font-size: 11px; color: var(--c-ink-3);
  width: 36px; text-align: right;
}
.tint-row { display: flex; gap: 6px; flex: 1; }
.tint-swatch {
  width: 22px; height: 22px; border-radius: 50%;
  border: 2px solid transparent; cursor: pointer;
  transition: transform var(--t-fast), border-color var(--t-fast);
  flex-shrink: 0;
}
.tint-swatch:hover { transform: scale(1.12); }
.tint-swatch.active {
  border-color: var(--c-ink);
  transform: scale(1.12);
}
.set-reset {
  margin-top: 4px;
  padding: 6px 10px;
  background: var(--glass-2-bg);
  border: 1px solid var(--c-line);
  border-radius: var(--r-sm);
  font-size: 12px; color: var(--c-ink-2);
  cursor: pointer;
  transition: background var(--t-fast);
}
.set-reset:hover { background: var(--glass-1-bg); color: var(--c-ink); }
</style>