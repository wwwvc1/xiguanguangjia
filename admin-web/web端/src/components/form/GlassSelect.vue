<script setup lang="ts">
/**
 * GlassSelect — 玻璃下拉 (Phase 0 占位)
 */
interface Option { label: string; value: string | number }
interface Props {
  modelValue?: string | number
  options: Option[]
  placeholder?: string
}
defineProps<Props>()
defineEmits<{ (e: 'update:modelValue', v: string | number): void }>()
</script>

<template>
  <label class="g-select">
    <select
      :value="modelValue"
      @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value as any)"
    >
      <option v-if="placeholder" :value="''" disabled>{{ placeholder }}</option>
      <option v-for="opt in options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
    </select>
    <span class="caret">⌄</span>
  </label>
</template>

<style scoped>
.g-select {
  display: block; position: relative;
}
.g-select select {
  width: 100%;
  padding: 12px 36px 12px 16px;
  border-radius: var(--r-sm);
  background: var(--glass-3-bg);
  border: 1px solid var(--c-line);
  color: var(--c-ink);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  appearance: none;
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.g-select select:focus {
  border-color: var(--accent-1);
  box-shadow: 0 0 0 3px rgba(124, 92, 255, 0.18);
}
.caret {
  position: absolute;
  right: 14px; top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
  color: var(--c-ink-3);
  font-size: 12px;
}
</style>