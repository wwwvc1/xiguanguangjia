/**
 * 知识库 (RAG) API
 *
 * 端点(对应 backend/routers/admin_knowledge.py):
 *   GET    /api/admin/knowledge/documents?source=static|uploaded
 *   POST   /api/admin/knowledge/upload
 *   DELETE /api/admin/knowledge/documents/{id}    (id 是字符串,upload_5 或 static_xxx.md)
 *   POST   /api/admin/knowledge/documents/{id}/reindex
 *   GET    /api/admin/knowledge/preview/{id}?max_chars=2000
 *   POST   /api/admin/knowledge/test-search?query=...&top_k=3
 *   GET    /api/admin/knowledge/documents/{id}/content    (完整原文,供编辑器)
 *   PUT    /api/admin/knowledge/documents/{id}/content    (保存原文,自动 reindex)
 *
 * id 约定:静态="static_<filename>";上传="upload_<int>"
 */
import http from './http'

// ────────────────────────── 类型 ──────────────────────────

export interface KnowledgeDoc {
  /** 字符串 id,前缀区分来源 */
  id: string
  source: 'static' | 'uploaded'
  filename: string
  chunk_count: number
  size_bytes: number
  status: 'pending' | 'indexed' | 'failed' | string
  error_msg: string | null
  uploaded_by: number | null
  created_at: string | null
  updated_at: string | null
  editable: boolean
  deletable: boolean
}

export interface KnowledgeListResp {
  documents: KnowledgeDoc[]
}

export interface KnowledgePreview {
  id: string
  filename: string
  content: string
  truncated: boolean
}

export interface KnowledgeContent {
  id: string
  filename: string
  content: string
  truncated: boolean
}

export interface KnowledgeSearchHit {
  text: string
  filename: string | null
  doc_id: number | string | null
  distance: number | null
}

export interface KnowledgeSearchResp {
  query: string
  results: KnowledgeSearchHit[]
}

// ────────────────────────── 列表 / 上传 / 删除 ──────────────────────────

/** 文档列表,支持 source / status 过滤 */
export function listDocuments(params: {
  source?: 'static' | 'uploaded'
  status?: 'indexed' | 'pending' | 'failed'
} = {}): Promise<KnowledgeDoc[]> {
  const q: Record<string, string> = {}
  if (params.source) q.source = params.source
  if (params.status) q.status = params.status
  return http
    .get<KnowledgeListResp>('/admin/knowledge/documents', { params: q })
    .then((r) => r.data.documents ?? [])
}

/** 上传 .md / .txt */
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

/** 删除(只允许上传的) */
export function deleteDocument(id: string): Promise<{ message: string; id: string }> {
  return http
    .delete<{ message: string; id: string }>(`/admin/knowledge/documents/${id}`)
    .then((r) => r.data)
}

/** 重新索引 */
export function reindexDocument(id: string): Promise<KnowledgeDoc> {
  return http
    .post<KnowledgeDoc>(`/admin/knowledge/documents/${id}/reindex`)
    .then((r) => r.data)
}

/** 预览前 N 字符 */
export function previewDocument(id: string, maxChars = 2000): Promise<KnowledgePreview> {
  return http
    .get<KnowledgePreview>(`/admin/knowledge/preview/${id}`, { params: { max_chars: maxChars } })
    .then((r) => r.data)
}

/** 获取完整原文(供编辑器初始化) */
export function getDocumentContent(id: string): Promise<KnowledgeContent> {
  return http
    .get<KnowledgeContent>(`/admin/knowledge/documents/${id}/content`)
    .then((r) => r.data)
}

/** 保存原文(写盘 + 自动 reindex) */
export function updateDocumentContent(id: string, content: string): Promise<{
  id: string
  source: 'static' | 'uploaded'
  filename: string
  chunk_count: number
  message: string
}> {
  return http
    .put(`/admin/knowledge/documents/${id}/content`, { content })
    .then((r) => r.data)
}

// ────────────────────────── 搜索预览 ──────────────────────────

export function testKnowledgeSearch(query: string, topK = 3): Promise<KnowledgeSearchResp> {
  return http
    .post<KnowledgeSearchResp>('/admin/knowledge/test-search', null, {
      params: { query, top_k: topK }
    })
    .then((r) => r.data)
}
