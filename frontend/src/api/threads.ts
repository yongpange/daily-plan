import http from './http'
import type { DayResponse } from '../types/api'

export interface CreateThreadPayload {
  date: string
  title: string
  done_when: string
  step: string
  project_name?: string
  estimate_minutes?: number
}

export function createThread(payload: CreateThreadPayload) {
  return http.post<DayResponse>('/threads', payload).then((r) => r.data)
}

export interface UpdateThreadPayload {
  title?: string
  done_when?: string
  status?: 'active' | 'paused' | 'done'
  featured?: boolean
  project_name?: string
  date?: string
}

export function updateThread(threadId: number, payload: UpdateThreadPayload) {
  return http.patch<DayResponse>(`/threads/${threadId}`, payload).then((r) => r.data)
}

export function createThreadStep(threadId: number, payload: { date: string; step: string; estimate_minutes?: number }) {
  return http.post<DayResponse>(`/threads/${threadId}/steps`, payload).then((r) => r.data)
}
