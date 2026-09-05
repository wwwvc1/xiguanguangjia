<script setup lang="ts">
import { onMounted } from 'vue'
import { useThemeStore } from '@/stores/theme'

const theme = useThemeStore()

onMounted(() => {
  // 移除 index.html 中的启动占位,避免 vue 接管后残留
  const loading = document.getElementById('app-loading')
  loading?.remove()
})
</script>

<template>
  <router-view v-slot="{ Component, route }">
    <transition name="fade-page" mode="out-in">
      <component :is="Component" :key="route.fullPath" />
    </transition>
  </router-view>
</template>

<style>
/* =========================================================
 * Design Tokens (继承自 16-混合-纯Canvas2D-高透玻璃.html)
 * Light 默认 + Dark 通过 [data-theme="dark"] 覆盖
 * ========================================================= */
:root,
:root[data-theme='light'] {
  /* 品牌主色 — 沉香玻璃的纸感 */
  --c-ink: #0f1a14;
  --c-ink-2: #1a2a20;
  --c-ink-3: #4a5a52;
  --c-paper: #efe9dd;
  --c-paper-2: #e8e0d0;
  --c-agar: #142a20;
  --c-agar-2: #1f3d2d;
  --c-bone: #d8c9a5;
  --c-brick: #8e3d2a;
  --c-line: rgba(15, 26, 20, 0.08);

  /* Accent 紫青渐变 */
  --accent-1: #7c5cff;
  --accent-2: #34d399;
  --accent-3: #60a5fa;
  --accent-4: #f472b6;
  --accent-glow: 0 0 24px rgba(124, 92, 255, 0.45);
  --accent-gradient: linear-gradient(135deg, var(--accent-1), var(--accent-2));

  /* Glass 3 档 */
  --glass-1-bg: rgba(255, 255, 255, 0.55);
  --glass-1-border: rgba(255, 255, 255, 0.65);
  --glass-1-shadow: 0 8px 32px rgba(15, 26, 20, 0.10);

  --glass-2-bg: rgba(255, 255, 255, 0.75);

  /* 弹窗背景:不透明(避免透到背后页面),0~1 数字可调 */
  --modal-bg: rgba(255, 255, 255, 0.96);
  --modal-mask: rgba(0, 0, 0, 0.5);
  --glass-2-border: rgba(255, 255, 255, 0.85);
  --glass-2-shadow: 0 4px 16px rgba(15, 26, 20, 0.08);

  --glass-3-bg: rgba(255, 255, 255, 0.92);
  --glass-3-border: rgba(255, 255, 255, 0.95);
  --glass-3-shadow: 0 2px 8px rgba(15, 26, 20, 0.06);

  --glass-blur-1: 40px;
  --glass-blur-2: 20px;
  --glass-blur-3: 0px;

  /* Radius */
  --r-sm: 12px;
  --r-md: 18px;
  --r-lg: 24px;
  --r-pill: 999px;

  /* 字体 */
  --font-serif: 'Georgia', 'Times New Roman', 'Noto Serif CJK SC', 'PingFang SC', serif;
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --font-mono: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;

  /* 状态色 */
  --state-success: #22c55e;
  --state-warning: #eab308;
  --state-error: #f87171;
  --state-info: #38bdf8;

  /* 过渡 */
  --t-fast: 0.18s cubic-bezier(0.4, 0, 0.2, 1);
  --t-med: 0.4s cubic-bezier(0.4, 0, 0.2, 1);

  /* Layout */
  --nav-width: 220px;
  --rightbar-width: 300px;
  --topbar-height: 64px;
}

:root[data-theme='dark'] {
  --c-ink: #e8efe9;
  --c-ink-2: #c8d4cc;
  --c-ink-3: #8a948e;
  --c-paper: #06070b;
  --c-paper-2: #0a0f0c;
  --c-line: rgba(255, 255, 255, 0.06);

  --glass-1-bg: rgba(20, 22, 30, 0.4);
  --glass-1-border: rgba(255, 255, 255, 0.06);
  --glass-1-shadow: 0 8px 32px rgba(0, 0, 0, 0.55);

  --glass-2-bg: rgba(20, 22, 30, 0.55);

  /* 弹窗背景(深色模式) */
  --modal-bg: rgba(15, 18, 26, 0.96);
  --modal-mask: rgba(0, 0, 0, 0.6);
  --glass-2-border: rgba(255, 255, 255, 0.08);
  --glass-2-shadow: 0 4px 16px rgba(0, 0, 0, 0.40);

  --glass-3-bg: rgba(15, 18, 25, 0.92);
  --glass-3-border: rgba(255, 255, 255, 0.10);
  --glass-3-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
}

/* ===== Reset ===== */
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body, #app { height: 100%;background: var(--c-paper); }
body {
  font-family: var(--font-sans);
  background: var(--c-paper);
  color: var(--c-ink);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  overflow-x: hidden;
  transition: background var(--t-med), color var(--t-med);
}
[data-theme='dark'] body {
  background:
    radial-gradient(ellipse at 20% 30%, rgba(124, 92, 255, 0.10) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 70%, rgba(52, 211, 153, 0.08) 0%, transparent 50%),
    var(--c-paper);
}
a { color: inherit; text-decoration: none; }
button { font: inherit; cursor: pointer; }

/* ===== 路由切换 ===== */
.fade-page-enter-active,
.fade-page-leave-active {
  transition: opacity 0.28s ease, transform 0.28s cubic-bezier(0.16, 1, 0.3, 1);
}
.fade-page-enter-from { opacity: 0; transform: translateY(8px); }
.fade-page-leave-to { opacity: 0; transform: translateY(-4px); }

/* ===== 工具类 ===== */
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
.serif { font-family: var(--font-serif); }
.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }

/* 玻璃卡 hover 抬升(动效 2,从 16 套移植) */
.glass-2,
.glass-3,
.login-card,
.kpi-card,
.stat-card,
.panel-card {
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.glass-2:hover,
.glass-3:hover,
.login-card:hover,
.kpi-card:hover,
.stat-card:hover,
.panel-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 18px 40px -10px rgba(124, 92, 255, 0.28), inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}
</style>