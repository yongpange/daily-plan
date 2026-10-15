// localStorage 键名与旧实现保持一致（web-legacy/app.js STORAGE 表）
export const STORAGE = {
  view: 'daily-plan:view',
  date: 'daily-plan:selected-date',
  timer: 'daily-plan:timer-checkpoint',
  reportPeriod: 'daily-plan:report-period',
  focusMinutes: 'daily-plan:focus-minutes',
  breakMinutes: 'daily-plan:break-minutes',
  breakUntil: 'daily-plan:break-until',
} as const

// SQLite 是业务数据的唯一权威来源，本地偏好失败不影响记录。
export function safeStorageGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function safeStorageSet(key: string, value: string | number) {
  try {
    window.localStorage.setItem(key, String(value))
  } catch {
    // 忽略
  }
}

export function safeStorageRemove(key: string) {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // 忽略
  }
}
