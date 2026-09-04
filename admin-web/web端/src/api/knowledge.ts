/**
 * 知识库 (RAG) API
 *
 * 端点(对应 backend/routers/admin_knowledge.py):
 *   GET    /api/admin/knowledge/documents?is_active=true|false
 *   POST   /api/admin/knowledge/upload                (multipart/form-data)
 *   DELETE /api/admin/knowledge/documents/{id}
 *   POST   /api/admin/knowledge/documents/{id}/reindex
 *   GET    /api/admin/knowledge/preview/{id}?max_chars=2000
 *   POST   /api/admin/knowledge/test-search?query=...&top_k=3
 */
import http from './http'

// ────────────────────────── 类型 ──────────────────────────

/** 知识库文档(列表项) */
export interface KnowledgeDoc {
  id: number
  filename: string
  storage_path: string
  chunk_count: number
  status: 'pending' | 'indexed' | 'failed' | string
  error_msg: string | null
  uploaded_by: number
  created_at: string | null
  updated_at: string | null
}

/** 文档列表响应 */
export interface KnowledgeListResp {
  documents: KnowledgeDoc[]
}

/** 预览响应 */
export interface KnowledgePreview {
  id: number
  filename: string
  content: string
  truncated: boolean
}

/** 单条召回 chunk(test-search) */
export interface KnowledgeSearchHit {
  text: string
  filename: string | null
  doc_id: number | string | null
  distance: number | null
}

/** 搜索响应 */
export interface KnowledgeSearchResp {
  query: string
  results: KnowledgeSearchHit[]
}

// ────────────────────────── 列表 / 上传 / 删除 ──────────────────────────

/** 文档列表 */
export function listDocuments(isActive?: boolean): Promise<KnowledgeDoc[]> {
  return http
    .get<KnowledgeListResp>('/admin/knowledge/documents', {
      params: isActive !== undefined ? { is_active: isActive } : {}
    })
    .then((r) => r.data.documents ?? [])
}

/** 上传文档(.md / .txt) */
export function uploadDocument(
  file: File,
  onUploadProgress?: (pct: number) => void
): Promise<KnowledgeDoc> {
  const form = new FormData()
  form.append('file', file)
  return http
    .post<KnowledgeDoc>('/admin/knowledge/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (onUploadProgress && e.total) onUploadProgress(Math.round((e.loaded / e.total) * 100))
      }
    })
    .then((r) => r.data)
}

/** 删除 */
export function deleteDocument(id: number): Promise<{ message: string; id: number }> {
  return http.delete<{ message: string; id: number }>(`/admin/knowledge/documents/${id}`).then((r) => r.data)
}

/** 重新索引 */
export function reindexDocument(id: number): Promise<KnowledgeDoc> {
  return http.post<KnowledgeDoc>(`/admin/knowledge/documents/${id}/reindex`).then((r) => r.data)
}

/** 预览前 N 字符 */
export function previewDocument(id: number, maxChars = 2000): Promise<KnowledgePreview> {
  return http
    .get<KnowledgePreview>(`/admin/knowledge/preview/${id}`, { params: { max_chars: maxChars } })
    .then((r) => r.data)
}

// ────────────────────────── 搜索预览 ──────────────────────────

/** RAG 测试搜索(query + top_k) */
export function testKnowledgeSearch(query: string, topK = 3): Promise<KnowledgeSearchResp> {
  return http
    .post<KnowledgeSearchResp>('/admin/knowledge/test-search', null, {
      params: { query, top_k: topK }
    })
    .then((r) => r.data)
}
