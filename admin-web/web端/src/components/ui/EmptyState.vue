<script setup lang="ts">
/**
 * EmptyState — 空状态占位
 */
interface Props {
  icon?: string
  title?: string
  hint?: string
}
withDefaults(defineProps<Props>(), {
  icon: '◌',
  title: '暂无数据',
  hint: ''
})
</script>

<template>
  <div class="empty">
    <div class="icon">{{ icon }}</div>
    <div class="title">{{ title }}</div>
    <div v-if="hint" class="hint">{{ hint }}</div>
    <div v-if="$slots.action" class="action"><slot name="action" /></div>
  </div>
</template>

<style scoped>
.empty {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center;
  padding: 48px 16px;
  gap: 8px;
  color: var(--c-ink-3);
  text-align: center;
}
.icon {
  font-size: 32px;
  opacity: 0.5;
  margin-bottom: 4px;
}
.title {
  font-size: 14px;
  font-weight: 500;
  color: var(--c-ink-2);
}
.hint {
  font-size: 12px;
  color: var(--c-ink-3);
  max-width: 320px;
}
.action { margin-top: 12px; }
</style>