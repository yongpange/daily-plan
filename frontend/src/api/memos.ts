import http from './http'
import type { Memo, MemoReadResult, MemoSource, MemoTemplate } from '../types/api'

export interface FetchMemosParams {
  date?: string
  query?: string
  limit?: number
  source_kind?: '' | 'routine' | 'thread'
  source_id?: number | string
  task_id?: number
}

export function fetchMemos(params: FetchMemosParams = {}) {
  const query: Record<string, string> = {}
  if (params.date) query.date = params.date
  if (params.query) query.query = params.query
  if (params.limit != null) query.limit = String(params.limit)
  if (params.source_kind) query.source_kind = params.source_kind
  if (params.source_id != null) query.source_id = String(params.source_id)
  if (params.task_id != null) query.task_id = String(params.task_id)
  return http.get<Memo[]>('/memos', { params: query }).then((r) => r.data)
}

export interface SaveMemoPayload {
  date?: string
  content: string
  content_format?: string
  tags?: string
  has_images?: boolean
  note_title?: string
  note_link?: string
  entry_id?: number
  routine_id?: number
  thread_id?: number
}

export function createMemo(payload: SaveMemoPayload) {
  return http.post<Memo>('/memos', payload).then((r) => r.data)
}

export function updateMemo(memoId: number, payload: Partial<SaveMemoPayload> & { pinned?: boolean }) {
  return http.patch<Memo>(`/memos/${memoId}`, payload).then((r) => r.data)
}

export function deleteMemo(memoId: number) {
  return http.delete<{ deleted: boolean }>(`/memos/${memoId}`).then((r) => r.data)
}

export function markMemoRead(kind: 'memo' | 'daily', id: number | string) {
  return http.post<MemoReadResult>('/memo-reads', { kind, id }).then((r) => r.data)
}

export function fetchMemoSources() {
  return http.get<MemoSource[]>('/memo-sources').then((r) => r.data)
}

export function fetchSuggestedTags() {
  return http.get<{ tags: string[] }>('/tags/suggested').then((r) => r.data)
}

export function fetchMemoTemplates() {
  return http.get<MemoTemplate[]>('/memo-templates').then((r) => r.data)
}

export function saveMemoTemplate(payload: { id?: number; name: string; content: string }) {
  if (payload.id != null) {
    return http.patch<MemoTemplate>(`/memo-templates/${payload.id}`, payload).then((r) => r.data)
  }
  return http.post<MemoTemplate>('/memo-templates', payload).then((r) => r.data)
}

export function deleteMemoTemplate(templateId: number) {
  return http.delete<{ deleted: boolean }>(`/memo-templates/${templateId}`).then((r) => r.data)
}
