// 管理员登录相关 API
import http from './http'

export const adminLogin = (username, password) => {
  return http.post('/admin/auth/login', { username, password })
}

export const adminMe = () => {
  return http.get('/admin/auth/me')
}

export const adminLogout = () => {
  return http.post('/admin/auth/logout')
}
