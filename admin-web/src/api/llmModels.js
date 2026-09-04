import http from './http'

export const listLLMModels = (params) => http.get('/admin/llm-models', { params })
export const createLLMModel = (data) => http.post('/admin/llm-models', data)
export const updateLLMModel = (id, data) => http.put(`/admin/llm-models/${id}`, data)
export const deleteLLMModel = (id) => http.delete(`/admin/llm-models/${id}`)
export const setDefaultLLMModel = (id) => http.post(`/admin/llm-models/${id}/set-default`)
export const testLLMModel = (id, prompt) => http.post(`/admin/llm-models/${id}/test`, { prompt })
