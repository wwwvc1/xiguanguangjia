import { ref, onMounted, onBeforeUnmount } from 'vue'

/**
 * 磁吸光带:跟随鼠标设置 --mx/--my CSS 变量,父元素 ::after 描边会跟着亮
 *
 * 用法:
 *   const ref = useMagneticHover()
 *   <div :ref="ref" class="magnetic">…</div>
 *
 * CSS:
 *   .magnetic { position: relative; }
 *   .magnetic::after {
 *     background: radial-gradient(circle at var(--mx,50%) var(--my,50%),
 *                                var(--accent-1), transparent 40%);
 *     opacity: 0; transition: opacity .25s;
 *   }
 *   .magnetic:hover::after { opacity: 1; }
 */
export function useMagneticHover<T extends HTMLElement = HTMLElement>() {
  const el = ref<T | null>(null)

  const onMove = (e: MouseEvent) => {
    const node = el.value
    if (!node) return
    const rect = node.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * 100
    const y = ((e.clientY - rect.top) / rect.height) * 100
    node.style.setProperty('--mx', `${x}%`)
    node.style.setProperty('--my', `${y}%`)
  }

  const onLeave = () => {
    const node = el.value
    if (!node) return
    node.style.setProperty('--mx', '50%')
    node.style.setProperty('--my', '50%')
  }

  onMounted(() => {
    const node = el.value
    if (!node) return
    node.addEventListener('mousemove', onMove)
    node.addEventListener('mouseleave', onLeave)
  })

  onBeforeUnmount(() => {
    const node = el.value
    if (!node) return
    node.removeEventListener('mousemove', onMove)
    node.removeEventListener('mouseleave', onLeave)
  })

  return el
}