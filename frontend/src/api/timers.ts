import http from './http'
import type { Segment, TimerStartResult, TimerStopResult } from '../types/api'

export interface StartTimerPayload {
  entry_id?: number
  routine_id?: number
  date?: string
  mode?: 'open' | 'focus'
  focus_minutes?: number
}

export function startTimer(payload: StartTimerPayload) {
  return http.post<TimerStartResult>('/timer/start', payload).then((r) => r.data)
}

export interface StopTimerPayload {
  entry_id?: number | null
  routine_id?: number
  target_reached?: boolean
}

export function stopTimer(payload: StopTimerPayload = {}) {
  return http.post<TimerStopResult>('/timer/stop', payload).then((r) => r.data)
}

export function fetchSegments(start?: string, end?: string) {
  return http.get<Segment[]>('/segments', { params: { start, end } }).then((r) => r.data)
}

export function updateSegment(segmentId: number, durationMinutes: number) {
  return http.patch<Segment>(`/segments/${segmentId}`, { duration_minutes: durationMinutes }).then((r) => r.data)
}

export function deleteSegment(segmentId: number) {
  return http.delete<{ deleted: boolean }>(`/segments/${segmentId}`).then((r) => r.data)
}
