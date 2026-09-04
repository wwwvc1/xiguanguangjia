<script setup lang="ts">
/**
 * GlassCard — 3 档玻璃卡 (继承自 16 套高透玻璃)
 *  - tier=1 → 外层高透 (rgba(255,255,255,0.08) + blur(40px) + 1px 边)
 *  - tier=2 → 中透    (rgba(255,255,255,0.5)  + blur(20px))
 *  - tier=3 → 实      (rgba(255,255,255,0.92) + 细腻阴影)
 *  - interactive=true → hover 抬升 + 增强阴影
 *  - magnetic=true     → 启用磁吸光带 (需要外层 useMagneticHover 注入 --mx/--my)
 *
 * 兼容旧 API: type='outer' | 'middle' | 'inner' (Phase 0 占位调用)
 */
import { computed } from 'vue'

interface Props {
  /** 新 API: 1=高透 / 2=中透 / 3=实 */
  tier?: 1 | 2 | 3
  /** 旧 API: outer/middle/inner → 1/2/3 映射 */
  type?: 'outer' | 'middle' | 'inner'
  /** hover 抬升 + 增强阴影 */
  interactive?: boolean
  /** 磁吸光带 (需 useMagneticHover 注入 --mx/--my) */
  magnetic?: boolean
  padding?: string
  radius?: string
  as?: keyof HTMLElementTagNameMap
}

const props = withDefaults(defineProps<Props>(), {
  tier: 2,
  interactive: false,
  magnetic: false,
  padding: '20px',
  radius: 'var(--r-md)',
  as: 'div'
})

// 兼容旧 type 字段
const resolvedTier = computed<1 | 2 | 3>(() => {
  if (props.type === 'outer') return 1
  if (props.type === 'inner') return 3
  return props.tier
})

const klass = computed(() => [
  `glass-tier-${resolvedTier.value}`,
  { 'is-interactive': props.interactive, magnetic: props.magnetic }
])

const style = computed(() => ({
  padding: props.padding,
  borderRadius: props.radius
}))
</script>

<template>
  <component :is="as" :class="klass" :style="style">
    <slot />
  </component>
</template>

<style scoped>
.glass-tier-1,
.glass-tier-2,
.glass-tier-3 {
  position: relative;
  border-radius: inherit;
  overflow: hidden;
  color: var(--c-ink);
}

/* ============ Tier 1 — 高透 ============ */
.glass-tier-1 {
  background: var(--glass-1-bg);
  backdrop-filter: blur(var(--glass-blur-1, 40px)) saturate(180%);
  -webkit-backdrop-filter: blur(var(--glass-blur-1, 40px)) saturate(180%);
  border: 1px solid var(--glass-1-border);
  box-shadow: var(--glass-1-shadow);
}

/* ============ Tier 2 — 中透 ============ */
.glass-tier-2 {
  background: var(--glass-2-bg);
  backdrop-filter: blur(var(--glass-blur-2, 20px)) saturate(160%);
  -webkit-backdrop-filter: blur(var(--glass-blur-2, 20px)) saturate(160%);
  border: 1px solid var(--glass-2-border);
  box-shadow: var(--glass-2-shadow);
}

/* ============ Tier 3 — 实 ============ */
.glass-tier-3 {
  background: var(--glass-3-bg);
  backdrop-filter: blur(var(--glass-blur-3, 0px));
  -webkit-backdrop-filter: blur(var(--glass-blur-3, 0px));
  border: 1px solid var(--glass-3-border);
  box-shadow: var(--glass-3-shadow);
}

/* ============ Hover 抬升 ============ */
.is-interactive {
  transition:
    transform 0.4s cubic-bezier(0.16, 1, 0.3, 1),
    box-shadow 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.is-interactive:hover {
  transform: translateY(-4px);
  box-shadow:
    0 18px 40px -10px rgba(124, 92, 255, 0.28),
    inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}

/* ============ 磁吸光带 ============ */
.magnetic::after {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: inherit;
  padding: 1px;
  background: radial-gradient(
    120px circle at var(--mx, 50%) var(--my, 50%),
    rgba(124, 92, 255, 0.55),
    rgba(52, 211, 153, 0.35) 40%,
    transparent 70%
  );
  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.3s ease;
}
.magnetic:hover::after {
  opacity: 1;
}
</style>