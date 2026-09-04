<script setup lang="ts">
/**
 * DonutChart — 环形图 (Phase 0 占位;Phase 1+ 用 SVG conic 实现)
 */
interface Props {
  data?: { label: string; value: number }[]
  size?: number
}
withDefaults(defineProps<Props>(), { data: () => [], size: 160 })
</script>

<template>
  <div class="donut-stub" :style="{ width: size + 'px', height: size + 'px' }">
    <div class="ring" />
    <div class="center">
      <slot>
        <div class="hint">Donut</div>
      </slot>
    </div>
  </div>
</template>

<style scoped>
.donut-stub {
  position: relative;
  border-radius: 50%;
  background: var(--glass-2-bg);
  display: grid; place-items: center;
}
.ring {
  position: absolute; inset: 8px;
  border-radius: 50%;
  background: conic-gradient(from -90deg, var(--accent-1), var(--accent-2), var(--accent-3), var(--accent-1));
  mask: radial-gradient(circle, transparent 50%, black 51%);
  -webkit-mask: radial-gradient(circle, transparent 50%, black 51%);
}
.center {
  position: relative;
  font-size: 12px; color: var(--c-ink-2);
}
.hint { letter-spacing: 0.06em; }
</style>