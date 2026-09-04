// 用户管理 API
import http from './http'

export const listUsers = (params) => http.get('/admin/users', { params })
export const getUserDetail = (id) => http.get(`/admin/users/${id}`)
export const deleteUser = (id) => http.delete(`/admin/users/${id}`)
export const toggleUserActive = (id, is_active) => http.patch(`/admin/users/${id}/active`, { is_active })
export const resetUserPassword = (id, new_password) => http.post(`/admin/users/${id}/reset-password`, { new_password })
export const updateUserQuota = (id, payload) => http.patch(`/admin/users/${id}/quota`, payload)
export const getUserAIChats = (id, params) => http.get(`/admin/users/${id}/ai-chats`, { params })
export const getUserAIChatDetail = (id, sessionId) => http.get(`/admin/users/${id}/ai-chats/${sessionId}`)
