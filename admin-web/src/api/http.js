// Axios HTTP 实例,带 token 拦截器
import axios from 'axios'
import { message } from 'ant-design-vue'

const http = axios.create({
  baseURL: '/api',
  timeout: 30000
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => {
    const data = response.data
    // FastAPI 直接返回业务数据,如有 {code, data} 走统一格式
    if (data && data.code !== undefined) {
      if (data.code === 200) return data.data
      if (data.code === 401) {
        localStorage.removeItem('admin_token')
        window.location.href = '/login'
        return Promise.reject(new Error('未授权'))
      }
      message.error(data.message || '请求失败')
      return Promise.reject(new Error(data.message))
    }
    return data
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('admin_token')
      window.location.href = '/login'
    } else if (error.response?.status === 403) {
      message.error('无权限访问')
    } else if (error.response?.status === 404) {
      message.error('资源不存在')
    } else if (error.response?.status >= 500) {
      message.error('服务器错误,请稍后再试')
    } else {
      message.error(error.response?.data?.detail || error.message || '网络错误')
    }
    return Promise.reject(error)
  }
)

export default http
