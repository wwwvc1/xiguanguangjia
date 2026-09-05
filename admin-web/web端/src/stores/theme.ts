import { defineStore } from 'pinia'

export type ThemeMode = 'light' | 'dark' | 'auto'

const STORAGE_KEY = 'admin-theme'
const MODAL_KEY = 'admin-modal-settings'

export interface ModalSettings {
  /** 弹窗背景 alpha,0~1。0.96 = 不透明,0.5 = 半透 */
  opacity: number
  /** 蒙层 alpha,0~1 */
  maskOpacity: number
  /** 主题色覆盖,null 表示跟随主题 */
  tint: string | null
}

const DEFAULT_MODAL: ModalSettings = {
  opacity: 0.96,
  maskOpacity: 0.5,
  tint: null
}

function resolveAuto(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'dark'
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(resolved: 'light' | 'dark') {
  document.documentElement.setAttribute('data-theme', resolved)
}

function applyModalSettings(s: ModalSettings) {
  // 把透明度 / 颜色写到 :root 上(覆盖 App.vue 的默认变量)
  const root = document.documentElement
  // 透明度保持 0~1
  const opacity = Math.max(0, Math.min(1, s.opacity))
  const mask = Math.max(0, Math.min(1, s.maskOpacity))
  if (s.tint) {
    // 有 tint:把背景写成 tint + 用户透明度
    root.style.setProperty('--modal-bg', hexToRgba(s.tint, opacity))
  } else {
    // 跟随主题:从根元素读 data-theme 决定深浅
    const dark = root.getAttribute('data-theme') === 'dark'
    const base = dark ? '15, 18, 26' : '255, 255, 255'
    root.style.setProperty('--modal-bg', `rgba(${base}, ${opacity})`)
  }
  root.style.setProperty('--modal-mask', `rgba(0, 0, 0, ${mask})`)
}

function hexToRgba(hex: string, alpha: number): string {
  // #rrggbb → rgba(r, g, b, a)
  const m = hex.replace('#', '').match(/^([0-9a-fA-F]{6})$/)
  if (!m) return `rgba(128, 128, 128, ${alpha})`
  const n = parseInt(m[1], 16)
  return `rgba(${(n >> 16) & 0xff}, ${(n >> 8) & 0xff}, ${n & 0xff}, ${alpha})`
}

export const useThemeStore = defineStore('theme', {
  state: () => ({
    mode: 'auto' as ThemeMode,
    modal: { ...DEFAULT_MODAL } as ModalSettings
  }),

  getters: {
    resolved: (s): 'light' | 'dark' => (s.mode === 'auto' ? resolveAuto() : s.mode)
  },

  actions: {
    init() {
      // 主题模式
      try {
        const raw = localStorage.getItem(STORAGE_KEY)
        if (raw === 'light' || raw === 'dark' || raw === 'auto') this.mode = raw
      } catch { /* ignore */ }
      applyTheme(this.resolved)

      // 弹窗设置
      try {
        const raw = localStorage.getItem(MODAL_KEY)
        if (raw) {
          const obj = JSON.parse(raw)
          if (typeof obj.opacity === 'number') this.modal.opacity = obj.opacity
          if (typeof obj.maskOpacity === 'number') this.modal.maskOpacity = obj.maskOpacity
          if (obj.tint === null || typeof obj.tint === 'string') this.modal.tint = obj.tint
        }
      } catch { /* ignore */ }
      applyModalSettings(this.modal)

      // 主题切换时(如果 tint 跟随)重新应用弹窗
      if (typeof window !== 'undefined' && window.matchMedia) {
        const mq = window.matchMedia('(prefers-color-scheme: dark)')
        mq.addEventListener?.('change', () => {
          if (this.mode === 'auto') {
            applyTheme(this.resolved)
            applyModalSettings(this.modal)
          }
        })
      }
    },

    setTheme(mode: ThemeMode) {
      this.mode = mode
      try { localStorage.setItem(STORAGE_KEY, mode) } catch { /* ignore */ }
      applyTheme(this.resolved)
      applyModalSettings(this.modal)
    },

    toggle() {
      const next: ThemeMode = this.resolved === 'dark' ? 'light' : 'dark'
      this.setTheme(next)
    },

    setModal(s: Partial<ModalSettings>) {
      this.modal = { ...this.modal, ...s }
      try { localStorage.setItem(MODAL_KEY, JSON.stringify(this.modal)) } catch { /* ignore */ }
      applyModalSettings(this.modal)
    },

    resetModal() {
      this.modal = { ...DEFAULT_MODAL }
      try { localStorage.removeItem(MODAL_KEY) } catch { /* ignore */ }
      applyModalSettings(this.modal)
    }
  }
})
