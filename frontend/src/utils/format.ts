export function formatMinutes(minutes: number): string {
  const rounded = Math.max(0, Math.round(Number(minutes) || 0))
  if (rounded < 60) return `${rounded} 分钟`
  const hours = Math.floor(rounded / 60)
  const rest = rounded % 60
  return rest ? `${hours} 小时 ${rest} 分` : `${hours} 小时`
}

export function formatHours(minutes: number): string {
  const number = Math.max(0, Number(minutes) || 0)
  if (number === 0) return '0 小时'
  const hours = number / 60
  return `${hours >= 10 ? hours.toFixed(1) : hours.toFixed(2).replace(/0$/, '')} 小时`
}

export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(Number(seconds) || 0))
  const hours = String(Math.floor(total / 3600)).padStart(2, '0')
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, '0')
  const rest = String(total % 60).padStart(2, '0')
  return `${hours}:${minutes}:${rest}`
}

export function formatShortClock(value: string | null | undefined): string {
  if (!value) return '进行中'
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

/** 本地时间 YYYY-MM-DDTHH:MM（提醒表单用） */
export function localMinute(value: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`
}
