import http from './http'

export const listDocuments = (params) => http.get('/admin/knowledge/documents', { params })

export const uploadDocument = (file, onUploadProgress) => {
  const form = new FormData()
  form.append('file', file)
  return http.post('/admin/knowledge/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress
  })
}

export const deleteDocument = (id) => http.delete(`/admin/knowledge/documents/${id}`)
export const reindexDocument = (id) => http.post(`/admin/knowledge/documents/${id}/reindex`)
export const previewDocument = (id) => http.get(`/admin/knowledge/preview/${id}`)
export const testSearch = (query, topK = 3) =>
  http.post(`/admin/knowledge/test-search?query=${encodeURIComponent(query)}&top_k=${topK}`)
