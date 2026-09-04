import http from './http'

export const listLogs = (params) => http.get('/admin/logs', { params })
export const listLogActions = () => http.get('/admin/logs/actions')
export const getLogStats = (days = 7) => http.get('/admin/logs/stats', { params: { days } })
export const exportLogsUrl = (params) => {
  const q = new URLSearchParams(params || {}).toString()
  return '/admin/logs/export' + (q ? '?' + q : '')
}
