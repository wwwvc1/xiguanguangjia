/**
 * 公告 API (Phase 4)
 *  - GET    /admin/announcements?status=&type=&page=&page_size=
 *  - POST   /admin/announcements
 *  - PATCH  /admin/announcements/{id}
 *  - DELETE /admin/announcements/{id}
 */
import http from './http'

export type AnnouncementType = 'system' | 'activity' | 'maintenance'
export type AnnouncementStatus = 'draft' | 'scheduled' | 'active' | 'expired'

export interface Announcement {
  id: number
  title: string
  content: string
  type: AnnouncementType
  /** 优先级 1=最低 5=最高 */
  priority: 1 | 2 | 3 | 4 | 5
  /** 后端派生的展示状态(基于 start_at/end_at) */
  status: AnnouncementStatus
  start_at: string | null
  end_at: string | null
  /** 是否启用 */
  enabled: boolean
  created_by: string
  created_at: string
  updated_at: string
}

export interface AnnouncementUpsert {
  title: string
  content: string
  type: AnnouncementType
  priority?: 1 | 2 | 3 | 4 | 5
  start_at?: string | null
  end_at?: string | null
  enabled?: boolean
}

export interface AnnouncementListQuery {
  status?: AnnouncementStatus | 'all'
  type?: AnnouncementType | 'all'
  page?: number
  page_size?: number
}

export interface AnnouncementListResp {
  items: Announcement[]
  total: number
  page: number
  page_size: number
}

/** 列表 + 筛选 + 分页 */
export async function listAnnouncements(
  query: AnnouncementListQuery = {}
): Promise<AnnouncementListResp> {
  const r = await http.get<AnnouncementListResp>('/admin/announcements', {
    params: {
      status: query.status && query.status !== 'all' ? query.status : undefined,
      type: query.type && query.type !== 'all' ? query.type : undefined,
      page: query.page ?? 1,
      page_size: query.page_size ?? 20
    }
  })
  // 后端兼容:可能直接返回数组
  if (Array.isArray(r.data)) {
    return {
      items: r.data as unknown as Announcement[],
      total: (r.data as unknown as Announcement[]).length,
      page: 1,
      page_size: (r.data as unknown as Announcement[]).length
    }
  }
  return r.data
}

/** 创建 */
export async function createAnnouncement(payload: AnnouncementUpsert): Promise<Announcement> {
  const r = await http.post<Announcement>('/admin/announcements', payload)
  return r.data
}

/** 部分更新 */
export async function updateAnnouncement(
  id: number,
  patch: Partial<AnnouncementUpsert>
): Promise<Announcement> {
  const r = await http.patch<Announcement>(`/admin/announcements/${id}`, patch)
  return r.data
}

/** 删除 */
export async function deleteAnnouncement(id: number): Promise<void> {
  await http.delete(`/admin/announcements/${id}`)
}

/** 启用/停用 */
export async function toggleAnnouncement(id: number, enabled: boolean): Promise<void> {
  await http.patch(`/admin/announcements/${id}`, { enabled })
}