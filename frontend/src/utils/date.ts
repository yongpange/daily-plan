import type { ReportPeriod } from '../types/api'

export function localDateString(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function todayString(): string {
  return localDateString(new Date())
}

export function parseLocalDate(value: string): Date {
  return new Date(`${value}T00:00:00`)
}

export function shiftDate(value: string, days: number): string {
  const next = parseLocalDate(value)
  next.setDate(next.getDate() + days)
  return localDateString(next)
}

export function shiftPeriod(value: string, period: ReportPeriod, direction: number): string {
  const next = parseLocalDate(value)
  if (period === 'week') next.setDate(next.getDate() + direction * 7)
  if (period === 'month') next.setMonth(next.getMonth() + direction)
  if (period === 'quarter') next.setMonth(next.getMonth() + direction * 3)
  return localDateString(next)
}

export function formatMemoDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'short',
  }).format(parseLocalDate(value))
}

/** 周一为一周起点 */
export function weekBounds(date: string): { start: string; end: string } {
  const parsed = parseLocalDate(date)
  const day = parsed.getDay() || 7 // 周日记为 7
  const monday = new Date(parsed)
  monday.setDate(parsed.getDate() - day + 1)
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  return { start: localDateString(monday), end: localDateString(sunday) }
}

export function nextMonday(date: string): string {
  const parsed = parseLocalDate(date)
  const day = parsed.getDay() || 7
  parsed.setDate(parsed.getDate() + (8 - day) % 7 || 7)
  return localDateString(parsed)
}

export function formatMonthDay(date: string): string {
  const parsed = parseLocalDate(date)
  return `${parsed.getMonth() + 1}月${parsed.getDate()}日`
}
