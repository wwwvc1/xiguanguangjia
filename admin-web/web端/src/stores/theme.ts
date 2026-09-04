import { defineStore } from 'pinia'

export type ThemeMode = 'light' | 'dark' | 'auto'

const STORAGE_KEY = 'admin-theme'

function resolveAuto(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'dark'
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(resolved: 'light' | 'dark') {
  document.documentElement.setAttribute('data-theme', resolved)
}

export const useThemeStore = defineStore('theme', {
  state: () => ({
    mode: 'auto' as ThemeMode
  }),

  getters: {
    resolved: (s): 'light' | 'dark' => (s.mode === 'auto' ? resolveAuto() : s.mode)
  },

  actions: {
    init() {
      try {
        const raw = localStorage.getItem(STORAGE_KEY)
        if (raw === 'light' || raw === 'dark' || raw === 'auto') {
          this.mode = raw
        }
      } catch { /* ignore */ }
      applyTheme(this.resolved)

      // auto 模式监听系统切换
      if (typeof window !== 'undefined' && window.matchMedia) {
        const mq = window.matchMedia('(prefers-color-scheme: dark)')
        mq.addEventListener?.('change', () => {
          if (this.mode === 'auto') applyTheme(this.resolved)
        })
      }
    },

    setTheme(mode: ThemeMode) {
      this.mode = mode
      try { localStorage.setItem(STORAGE_KEY, mode) } catch { /* ignore */ }
      applyTheme(this.resolved)
    },

    toggle() {
      const next: ThemeMode = this.resolved === 'dark' ? 'light' : 'dark'
      this.setTheme(next)
    }
  }
})