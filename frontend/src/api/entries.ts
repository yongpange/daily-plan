import http from './http'
import type { Entry, EntryOutcome } from '../types/api'

export interface CreateEntryPayload {
  date: string
  title: string
  project_name?: string
  estimate_minutes?: number
  planned_start?: string
  definition?: string
  parent_entry_id?: number
}

export function createEntry(payload: CreateEntryPayload) {
  return http.post<Entry>('/entries', payload).then((r) => r.data)
}

export interface UpdateEntryPayload {
  title?: string
  project_name?: string
  estimate_minutes?: number
  planned_start?: string | null
  definition?: string | null
  outcome?: EntryOutcome
}

export function updateEntry(entryId: number, payload: UpdateEntryPayload) {
  return http.patch<Entry>(`/entries/${entryId}`, payload).then((r) => r.data)
}

export function deleteEntry(entryId: number) {
  return http.delete<{ deleted: boolean }>(`/entries/${entryId}`).then((r) => r.data)
}

export function moveEntry(entryId: number, date: string) {
  return http
    .post<{ moved_to: string; title: string; source_date: string }>(`/entries/${entryId}/move`, { date })
    .then((r) => r.data)
}
