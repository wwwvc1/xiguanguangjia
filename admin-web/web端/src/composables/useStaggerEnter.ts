import { ref, onMounted, type Ref } from 'vue'

/**
 * 子元素 stagger 进入动画(8 城市入场效果,动效 6)
 * 用法:
 *   <div :ref="container" class="stagger-wrap">
 *     <div class="stagger-item" v-for="...">…</div>
 *   </div>
 *
 * CSS:
 *   .stagger-item { opacity: 0; transform: translateY(12px); }
 *   .stagger-item.in { animation: staggerIn .55s cubic-bezier(.16,1,.3,1) forwards; }
 *   @keyframes staggerIn { to { opacity: 1; transform: translateY(0); } }
 *
 * composable 会给每个 .stagger-item 加 .in 类并按 nth-child 设延迟
 */
export function useStaggerEnter(selector = '.stagger-item', baseDelay = 0.06): Ref<HTMLElement | null> {
  const container = ref<HTMLElement | null>(null)

  onMounted(() => {
    const root = container.value
    if (!root) return
    const items = root.querySelectorAll<HTMLElement>(selector)
    items.forEach((node, idx) => {
      node.style.animationDelay = `${baseDelay * idx}s`
      // 触发下一帧,让 animation 生效
      requestAnimationFrame(() => {
        node.classList.add('in')
      })
    })
  })

  return container
}