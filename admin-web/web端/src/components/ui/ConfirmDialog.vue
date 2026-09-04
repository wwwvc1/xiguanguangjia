<script setup lang="ts">
/**
 * ConfirmDialog — 玻璃确认弹窗 (Phase 0 占位;Phase 1+ 接危险操作)
 */
import GlassModal from '@/components/glass/GlassModal.vue'

interface Props {
  open: boolean
  title?: string
  message?: string
  confirmText?: string
  cancelText?: string
  tone?: 'default' | 'danger'
}
withDefaults(defineProps<Props>(), {
  title: '确认操作',
  message: '',
  confirmText: '确认',
  cancelText: '取消',
  tone: 'default'
})

const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

const onConfirm = () => {
  emit('confirm')
  emit('update:open', false)
}
const onCancel = () => {
  emit('cancel')
  emit('update:open', false)
}
</script>

<template>
  <GlassModal :open="open" :title="title" @update:open="(v) => emit('update:open', v)" width="420px">
    <p class="msg">{{ message }}</p>
    <template #footer>
      <button class="btn ghost" @click="onCancel">{{ cancelText }}</button>
      <button class="btn" :class="tone === 'danger' ? 'danger' : 'primary'" @click="onConfirm">
        {{ confirmText }}
      </button>
    </template>
  </GlassModal>
</template>

<style scoped>
.msg { font-size: 14px; color: var(--c-ink-2); line-height: 1.6; }
.btn {
  padding: 8px 16px;
  border-radius: var(--r-sm);
  font-size: 13px;
  font-weight: 500;
  border: none;
  transition: opacity var(--t-fast);
}
.btn.primary {
  background: var(--accent-gradient);
  color: #fff;
}
.btn.danger {
  background: var(--state-error);
  color: #fff;
}
.btn.ghost {
  background: var(--glass-1-bg);
  color: var(--c-ink-2);
}
.btn:hover { opacity: 0.85; }
</style>