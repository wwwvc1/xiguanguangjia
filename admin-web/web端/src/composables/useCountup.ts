import { ref, watch, onUnmounted, type Ref } from 'vue'

/**
 * 数字滚动动画 (easeOutQuart, 默认 1200ms)
 *
 * 用法 A — Ref 源:
 *   const src = ref(0)
 *   const display = useCountup(src)
 *   <span>{{ display }}</span>
 *
 * 用法 B — 函数源:
 *   const display = useCountup(() => props.value)
 *
 * 用法 C — 完成回调:
 *   const display = useCountup(src, 1500, { onComplete: () => console.log('done') })
 */
export interface CountupOptions {
  /** 动画时长 (ms) */
  duration?: number
  /** 小数位 (默认整数) */
  decimals?: number
  /** 完成回调 */
  onComplete?: () => void
  /** 起始值 (默认 0) */
  from?: number
}

export function useCountup(
  source: Ref<number> | (() => number),
  durationOrOptions: number | CountupOptions = 1200,
  legacyOnComplete?: () => void
): Ref<string> {
  // 兼容旧签名: useCountup(source, duration, onComplete)
  let duration = 1200
  let onComplete: (() => void) | undefined
  let decimals: number | undefined

  if (typeof durationOrOptions === 'number') {
    duration = durationOrOptions
    onComplete = legacyOnComplete
  } else {
    duration = durationOrOptions.duration ?? 1200
    onComplete = durationOrOptions.onComplete
    decimals = durationOrOptions.decimals
  }

  const initial = typeof source === 'function' ? source() : source.value
  const display = ref(formatValue(initial, decimals))
  let raf = 0
  let start = 0
  let fromVal = 0
  let toVal = 0

  const easeOutQuart = (t: number) => 1 - Math.pow(1 - t, 4)

  const tick = (now: number) => {
    if (!start) start = now
    const elapsed = now - start
    const t = Math.min(1, elapsed / duration)
    const v = fromVal + (toVal - fromVal) * easeOutQuart(t)
    display.value = formatValue(v, decimals)
    if (t < 1) {
      raf = requestAnimationFrame(tick)
    } else {
      display.value = formatValue(toVal, decimals)
      start = 0
      onComplete?.()
    }
  }

  const update = (next: number) => {
    cancelAnimationFrame(raf)
    fromVal = parseFloat(display.value.replace(/,/g, '')) || 0
    toVal = Number.isFinite(next) ? next : 0
    start = 0
    raf = requestAnimationFrame(tick)
  }

  const read = typeof source === 'function' ? source : () => source.value
  watch(read, (v) => update(Number(v) || 0))

  onUnmounted(() => cancelAnimationFrame(raf))

  return display
}

function formatValue(n: number, decimals?: number): string {
  if (decimals !== undefined && decimals > 0) {
    return n.toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    })
  }
  return Math.round(n).toLocaleString('en-US')
}

/** 直接 DOM 操作版本(给非 Vue 场景使用,例如纯 vanilla HTML) */
export function countup(
  el: HTMLElement,
  target: number,
  opts: { duration?: number; decimals?: number; suffix?: string; onComplete?: () => void } = {}
): void {
  const duration = opts.duration ?? 1200
  const decimals = opts.decimals
  const suffix = opts.suffix ?? ''
  const start = performance.now()
  const from = parseFloat((el.dataset.from || '0').replace(/,/g, '')) || 0

  const step = (now: number) => {
    const t = Math.min(1, (now - start) / duration)
    const eased = 1 - Math.pow(1 - t, 4)
    const cur = from + (target - from) * eased
    const text =
      decimals !== undefined ? cur.toFixed(decimals) : Math.round(cur).toLocaleString()
    el.textContent = text + suffix
    el.dataset.from = text
    if (t < 1) {
      requestAnimationFrame(step)
    } else {
      el.textContent =
        (decimals !== undefined ? target.toFixed(decimals) : target.toLocaleString()) + suffix
      opts.onComplete?.()
    }
  }
  requestAnimationFrame(step)
}