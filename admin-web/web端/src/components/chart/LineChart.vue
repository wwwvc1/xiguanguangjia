<script setup lang="ts">
/**
 * LineChart — 折线图 (Phase 0 占位)
 * Phase 1+ 接 echarts 或自绘 Canvas
 */
interface Props {
  data?: number[]
  labels?: string[]
  height?: number
}
withDefaults(defineProps<Props>(), { data: () => [], labels: () => [], height: 240 })
</script>

<template>
  <div class="chart-stub" :style="{ height: `${height}px` }">
    <div class="ph-row" v-for="i in 4" :key="i" :style="{ height: `${20 + i * 8}%` }" />
    <div class="hint">LineChart · Phase 1+ 接 echarts</div>
  </div>
</template>

<style scoped>
.chart-stub {
  position: relative;
  width: 100%;
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 16px;
  border-radius: var(--r-md);
  background: var(--glass-2-bg);
  border: 1px dashed var(--c-line);
}
.ph-row {
  flex: 1;
  background: linear-gradient(180deg, var(--accent-1), var(--accent-2));
  opacity: 0.25;
  border-radius: 4px 4px 0 0;
}
.hint {
  position: absolute;
  bottom: 8px; right: 12px;
  font-size: 11px;
  color: var(--c-ink-3);
  letter-spacing: 0.04em;
}
</style>