// Pinia auth store
import { defineStore } from 'pinia'
import { adminLogin as apiLogin, adminMe as apiMe, adminLogout as apiLogout } from '@/api/admin'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('admin_token') || '',
    user: null
  }),

  actions: {
    async login(username, password) {
      const r = await apiLogin(username, password)
      this.token = r.access_token
      this.user = { id: r.user_id, username: r.username, nickname: r.nickname, avatar: r.avatar }
      localStorage.setItem('admin_token', r.access_token)
      return r
    },

    async fetchMe() {
      try {
        const me = await apiMe()
        this.user = me
        return me
      } catch (e) {
        this.logout()
        throw e
      }
    },

    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('admin_token')
    }
  }
})
