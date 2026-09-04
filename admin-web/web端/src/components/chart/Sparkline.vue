<script setup lang="ts">
/**
 * Sparkline — 折线微图 (Phase 1+ 接入 dashboard KPI 卡片)
 * Phase 0 用 SVG path 占位
 */
import { computed } from 'vue'

interface Props {
  data: number[]
  width?: number
  height?: number
  stroke?: string
}
const props = withDefaults(defineProps<Props>(), {
  width: 100,
  height: 28,
  stroke: 'var(--accent-1)'
})

const path = computed(() => {
  if (!props.data.length) return ''
  const min = Math.min(...props.data)
  const max = Math.max(...props.data)
  const range = max - min || 1
  const stepX = props.width / (props.data.length - 1 || 1)
  return props.data
    .map((v, i) => {
      const x = i * stepX
      const y = props.height - ((v - min) / range) * props.height
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
})
</script>

<template>
  <svg :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" class="spark">
    <path :d="path" :stroke="stroke" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round" />
  </svg>
</template>

<style scoped>
.spark { display: block; }
</style>