import http from './http'
import type { ImageMeta } from '../types/api'

export interface UploadImagePayload {
  owner_type: 'day' | 'memo'
  owner_key: string
  original: string // dataURL
  thumbnail: string // dataURL
  width?: number
  height?: number
}

export function uploadImage(payload: UploadImagePayload) {
  return http.post<ImageMeta>('/images', payload).then((r) => r.data)
}

export function deleteImage(imageId: number) {
  return http.delete<{ deleted: boolean }>(`/images/${imageId}`).then((r) => r.data)
}

/** 图片直出 URL（不经 axios），与旧实现一致 */
export function imageUrl(imageId: number, thumb = false) {
  return `/api/images/${imageId}${thumb ? '/thumb' : ''}`
}
