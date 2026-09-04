<script setup lang="ts">
/**
 * GlassModal — 玻璃模态 (Phase 0 占位;Phase 3 接 achievement / knowledge 表单)
 */
import { watch } from 'vue'

interface Props {
  open: boolean
  title?: string
  width?: string
}
const props = withDefaults(defineProps<Props>(), { width: '480px' })
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

watch(() => props.open, (v) => {
  document.body.style.overflow = v ? 'hidden' : ''
})

const close = () => emit('update:open', false)
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="mask" @click.self="close">
        <div class="dialog glass-2" :style="{ width }">
          <header class="dlg-header">
            <h3>{{ title }}</h3>
            <button class="x" @click="close" aria-label="关闭">×</button>
          </header>
          <div class="dlg-body"><slot /></div>
          <footer v-if="$slots.footer" class="dlg-footer"><slot name="footer" /></footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: grid; place-items: center;
  z-index: 100;
  padding: 16px;
}
.dialog {
  border-radius: var(--r-lg);
  max-width: 92vw;
  max-height: 88vh;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.dlg-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--c-line);
}
.dlg-header h3 { font-size: 15px; font-weight: 600; color: var(--c-ink); }
.x {
  background: transparent; border: none;
  font-size: 22px; color: var(--c-ink-3);
  width: 28px; height: 28px; border-radius: 50%;
  transition: background var(--t-fast);
}
.x:hover { background: var(--glass-1-bg); color: var(--c-ink); }

.dlg-body { padding: 20px; overflow: auto; }
.dlg-footer {
  padding: 12px 20px;
  border-top: 1px solid var(--c-line);
  display: flex; justify-content: flex-end; gap: 8px;
}

.modal-enter-active,
.modal-leave-active { transition: opacity 0.2s ease; }
.modal-enter-from,
.modal-leave-to { opacity: 0; }
.modal-enter-active .dialog,
.modal-leave-active .dialog { transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
.modal-enter-from .dialog,
.modal-leave-to .dialog { transform: scale(0.96) translateY(8px); }
</style>