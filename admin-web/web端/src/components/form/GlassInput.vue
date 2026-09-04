<script setup lang="ts">
/**
 * GlassInput — 玻璃输入框 (Phase 0 占位;Phase 1 接 v-model + 校验)
 */
interface Props {
  modelValue?: string
  placeholder?: string
  type?: string
  disabled?: boolean
}
withDefaults(defineProps<Props>(), { type: 'text' })
defineEmits<{ (e: 'update:modelValue', v: string): void }>()
</script>

<template>
  <label class="g-input">
    <input
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
  </label>
</template>

<style scoped>
.g-input { display: block; position: relative; }
.g-input input {
  width: 100%;
  padding: 12px 16px;
  border-radius: var(--r-sm);
  background: var(--glass-3-bg);
  border: 1px solid var(--c-line);
  color: var(--c-ink);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.g-input input::placeholder { color: var(--c-ink-3); }
.g-input input:focus {
  border-color: var(--accent-1);
  box-shadow: 0 0 0 3px rgba(124, 92, 255, 0.18);
}
.g-input input:disabled { opacity: 0.5; cursor: not-allowed; }
</style>