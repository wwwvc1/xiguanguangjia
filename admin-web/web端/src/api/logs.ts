/**
 * 系统日志 API (Phase 4)
 */
import http from './http'

export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

export interface LogEntry {
  id: number
  ts: string  // ISO
  level: LogLevel
  source: string  // 'auth' / 'llm' / 'admin' ...
  actor: string  // user id / system
  message: string
  meta?: Record<string, unknown>
}

export interface LogListQuery {
  page?: number
  page_size?: number
  level?: LogLevel
  source?: string
  keyword?: string
  start_ts?: string
  end_ts?: string
}

export interface LogListResp {
  items: LogEntry[]
  total: number
}

export function listLogs(_q: LogListQuery = {}): Promise<LogListResp> {
  throw new Error('not implemented')
}

export function exportLogs(_q: LogListQuery = {}): Promise<Blob> {
  throw new Error('not implemented')
}