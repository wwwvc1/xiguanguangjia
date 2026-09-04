/**
 * 数据洞察 API (Phase 5)
 */
import http from './http'

export interface InsightReport {
  id: number
  title: string
  period: 'daily' | 'weekly' | 'monthly'
  period_label: string
  summary: string
  highlights: string[]
  metrics: { label: string; value: number | string }[]
  generated_at: string
}

export interface FunnelStep {
  name: string
  count: number
  conversion_pct: number
}

export interface CorrelationRow {
  feature_a: string
  feature_b: string
  correlation: number  // -1..1
  sample_size: number
}

export function listReports(_period: InsightReport['period'] = 'weekly'): Promise<InsightReport[]> {
  throw new Error('not implemented')
}

export function getReport(_id: number): Promise<InsightReport> {
  throw new Error('not implemented')
}

export function generateReport(_period: InsightReport['period']): Promise<InsightReport> {
  throw new Error('not implemented')
}

export function getCheckinFunnel(_range: '7d' | '30d' = '30d'): Promise<FunnelStep[]> {
  throw new Error('not implemented')
}

export function getCorrelations(_range: '30d' | '90d' = '30d'): Promise<CorrelationRow[]> {
  throw new Error('not implemented')
}