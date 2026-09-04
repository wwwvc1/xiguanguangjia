<script setup lang="ts">
/**
 * CountupText — 数字滚动 (easeOutQuart 1.2s)
 * 接受 prop: value (number) → 自动滚动到目标值
 */
import { computed } from 'vue'
import { useCountup } from '@/composables/useCountup'

interface Props {
  value: number
  decimals?: number
  prefix?: string
  suffix?: string
}
const props = withDefaults(defineProps<Props>(), { decimals: 0 })

const sourceRef = computed(() => props.value)
const display = useCountup(sourceRef, { decimals: props.decimals })

const formatted = computed(() => display.value)
</script>

<template>
  <span class="countup mono">{{ prefix }}{{ formatted }}{{ suffix }}</span>
</template>

<style scoped>
.countup {
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
  letter-spacing: -0.01em;
}
</style>