import http from './http'
import type { ReportPeriod, ReportResponse } from '../types/api'

export function fetchReport(date?: string, period: ReportPeriod = 'week') {
  return http.get<ReportResponse>('/report', { params: { date, period } }).then((r) => r.data)
}

export function saveReview(period: ReportPeriod, start: string, content: string) {
  return http.post<{ period: ReportPeriod; start: string; content: string }>('/review', { period, start, content }).then((r) => r.data)
}
