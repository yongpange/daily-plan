import http from './http'
import type { Reminder } from '../types/api'

export function fetchReminders() {
  return http.get<Reminder[]>('/reminders').then((r) => r.data)
}

export function createReminder(payload: { message: string; remind_at: string }) {
  return http.post<Reminder>('/reminders', payload).then((r) => r.data)
}

export function updateReminder(reminderId: number, payload: { message?: string; remind_at?: string; status?: 'pending' | 'done' }) {
  return http.patch<Reminder>(`/reminders/${reminderId}`, payload).then((r) => r.data)
}

export function deleteReminder(reminderId: number) {
  return http.delete<{ deleted: boolean }>(`/reminders/${reminderId}`).then((r) => r.data)
}
