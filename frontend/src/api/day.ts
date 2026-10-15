import http from './http'
import type { CloseDecision, DayResponse, DayRow } from '../types/api'

export function fetchDay(date?: string) {
  return http.get<DayResponse>('/day', { params: date ? { date } : {} }).then((r) => r.data)
}

export interface DaySavePayload {
  date: string
  focus?: string
  reflection?: string
  mood?: number | null
}

export function saveDay(payload: DaySavePayload) {
  return http.post<DayRow>('/day/save', payload).then((r) => r.data)
}

export function closeDay(payload: DaySavePayload & { decisions: CloseDecision[] }) {
  return http.post<DayResponse>('/day/close', payload).then((r) => r.data)
}
