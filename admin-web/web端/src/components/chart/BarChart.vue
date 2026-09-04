<script setup lang="ts">
/**
 * BarChart — 柱状图 (Phase 0 占位)
 */
interface Props {
  data?: number[]
  labels?: string[]
  height?: number
}
withDefaults(defineProps<Props>(), { data: () => [], labels: () => [], height: 200 })
</script>

<template>
  <div class="chart-stub" :style="{ height: `${height}px` }">
    <div class="bar" v-for="(v, i) in (data.length ? data : [40, 65, 30, 80, 55, 70, 90])" :key="i"
         :style="{ height: v + '%' }" />
    <div class="hint">BarChart · Phase 1+ 接 echarts</div>
  </div>
</template>

<style scoped>
.chart-stub {
  position: relative;
  width: 100%;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 16px;
  border-radius: var(--r-md);
  background: var(--glass-2-bg);
  border: 1px dashed var(--c-line);
}
.bar {
  flex: 1;
  background: linear-gradient(180deg, var(--accent-3), var(--accent-1));
  border-radius: 4px 4px 0 0;
  opacity: 0.8;
  transition: opacity var(--t-fast);
}
.bar:hover { opacity: 1; }
.hint {
  position: absolute;
  bottom: 8px; right: 12px;
  font-size: 11px;
  color: var(--c-ink-3);
}
</style>