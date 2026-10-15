import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import type { ApiErrorBody } from '../types/api'

// 统一 axios 实例：baseURL、错误文案提取（{"error": "中文"}）、全局 loading 计数、可选 API Key
const http = axios.create({ baseURL: '/api', timeout: 30000 })

const API_KEY = (import.meta.env.VITE_DAILY_PLAN_API_KEY as string | undefined) ?? ''
if (API_KEY) {
  http.defaults.headers.common['X-API-Key'] = API_KEY
}

// 全局 loading 计数（>0 表示有请求在飞），由 ui store 订阅
let pendingCount = 0
const listeners = new Set<(count: number) => void>()

export function onPendingChange(listener: (count: number) => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function changePending(delta: number) {
  pendingCount = Math.max(0, pendingCount + delta)
  listeners.forEach((fn) => fn(pendingCount))
}

/** 从 AxiosError 里取出后端统一错误文案 */
export function errorMessage(err: unknown, fallback = '请求失败，请稍后重试'): string {
  const axErr = err as AxiosError<ApiErrorBody>
  if (axErr?.response?.data && typeof axErr.response.data.error === 'string') {
    return axErr.response.data.error
  }
  if (axios.isAxiosError(err) && err.code === 'ECONNABORTED') return '请求超时，请稍后重试'
  if (axios.isAxiosError(err) && !err.response) return '无法连接服务器，请确认后端已启动'
  return fallback
}

http.interceptors.request.use((config) => {
  changePending(1)
  return config
})

http.interceptors.response.use(
  (response) => {
    changePending(-1)
    return response
  },
  (err) => {
    changePending(-1)
    return Promise.reject(err)
  },
)

export default http

export type { AxiosRequestConfig }
