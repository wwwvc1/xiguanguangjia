<script setup lang="ts">
/**
 * MagneticCard — 磁吸光带卡 (动效:鼠标跟随 + 径向渐变描边)
 * 继承自 16 套 .magnetic::after;通过 useMagneticHover 注入 --mx/--my
 */
import { useMagneticHover } from '@/composables/useMagneticHover'

interface Props {
  as?: keyof HTMLElementTagNameMap
  padding?: string
  radius?: string
  interactive?: boolean
}
withDefaults(defineProps<Props>(), {
  as: 'div',
  padding: '20px',
  radius: 'var(--r-md)',
  interactive: true
})

const ref = useMagneticHover<HTMLElement>()
</script>

<template>
  <component
    :is="as"
    :ref="ref"
    class="magnetic-card"
    :class="{ interactive }"
    :style="{ padding, borderRadius: radius }"
  >
    <slot />
  </component>
</template>

<style scoped>
.magnetic-card {
  position: relative;
  overflow: hidden;
  background: var(--glass-2-bg);
  backdrop-filter: blur(var(--glass-blur-2)) saturate(160%);
  -webkit-backdrop-filter: blur(var(--glass-blur-2)) saturate(160%);
  border: 1px solid var(--glass-2-border);
  box-shadow: var(--glass-2-shadow);
  color: var(--c-ink);
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

/* 磁吸光带 — 跟随 --mx / --my */
.magnetic-card::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: radial-gradient(
    circle at var(--mx, 50%) var(--my, 50%),
    var(--accent-1),
    transparent 35%
  );
  -webkit-mask:
    linear-gradient(#fff 0 0) content-box,
    linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  opacity: 0;
  transition: opacity var(--t-fast);
  pointer-events: none;
}

.magnetic-card.interactive:hover {
  transform: translateY(-4px);
  box-shadow:
    0 18px 40px -10px rgba(124, 92, 255, 0.28),
    inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}
.magnetic-card.interactive:hover::after {
  opacity: 0.9;
}
</style>