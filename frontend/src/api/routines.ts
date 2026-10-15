import http from './http'
import type { PublicRoutine, RoutineChallenge, RoutineDay } from '../types/api'

export function createRoutine(payload: { title: string; note?: string; estimate_minutes?: number }) {
  return http.post<PublicRoutine>('/routines', payload).then((r) => r.data)
}

export function updateRoutine(routineId: number, payload: { title?: string; note?: string; estimate_minutes?: number; unlock_token: string }) {
  return http.patch<PublicRoutine>(`/routines/${routineId}`, payload).then((r) => r.data)
}

export function deleteRoutine(routineId: number, unlockToken: string) {
  return http.delete<{ deleted: boolean }>(`/routines/${routineId}`, { data: { unlock_token: unlockToken } }).then((r) => r.data)
}

export function checkRoutine(routineId: number, date: string, completed: boolean) {
  return http.post<{ date: string; routines: RoutineDay[] }>('/routines/check', { routine_id: routineId, date, completed }).then((r) => r.data)
}

export function startRoutineTimer(routineId: number, date: string) {
  return http
    .post<{ already_running: boolean; stopped_entry_id: number | null; date: string; routines: RoutineDay[] }>(
      '/routines/timer/start',
      { routine_id: routineId, date },
    )
    .then((r) => r.data)
}

export function stopRoutineTimer(routineId: number) {
  return http
    .post<{ stopped: boolean; duration_seconds: number; date: string; routines: RoutineDay[] }>('/routines/timer/stop', {
      routine_id: routineId,
    })
    .then((r) => r.data)
}

export function createChallenge() {
  return http.post<RoutineChallenge>('/routines/challenge', {}).then((r) => r.data)
}

export function verifyChallenge(id: number, answers: number[]) {
  return http
    .post<{ unlocked: boolean; unlock_token: string; expires_at: string }>('/routines/challenge/verify', { id, answers })
    .then((r) => r.data)
}
