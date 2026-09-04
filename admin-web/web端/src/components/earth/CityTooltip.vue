<script setup lang="ts">
/**
 * CityTooltip — 鼠标悬停在地球上城市时弹出的玻璃提示
 */
interface Props {
  city?: { name: string; value: number; unit?: string }
  x?: number
  y?: number
}
withDefaults(defineProps<Props>(), { x: 0, y: 0 })
</script>

<template>
  <div v-if="city" class="city-tip glass-3" :style="{ left: x + 'px', top: y + 'px' }">
    <div class="name">{{ city.name }}</div>
    <div class="value mono">
      {{ city.value.toLocaleString() }}<span class="unit">{{ city.unit ?? '' }}</span>
    </div>
  </div>
</template>

<style scoped>
.city-tip {
  position: absolute;
  pointer-events: none;
  padding: 8px 12px;
  border-radius: var(--r-sm);
  transform: translate(-50%, calc(-100% - 12px));
  white-space: nowrap;
  z-index: 50;
}
.name { font-size: 12px; color: var(--c-ink-2); margin-bottom: 2px; }
.value { font-size: 16px; font-weight: 600; color: var(--c-ink); }
.unit { font-size: 11px; color: var(--c-ink-3); margin-left: 4px; }
</style>