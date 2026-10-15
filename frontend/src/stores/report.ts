import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import * as reportsApi from '../api/reports'
import * as timersApi from '../api/timers'
import type { ReportPeriod, ReportResponse, Segment } from '../types/api'
import { localDateString, shiftPeriod, weekBounds } from '../utils/date'
import { safeStorageSet, STORAGE } from '../utils/storage'
import { useTimerStore } from './timer'
import { useDayStore } from './day'

export const useReportStore = defineStore('report', () => {
  const period = ref<ReportPeriod>(
    (localStorage.getItem(STORAGE.reportPeriod) as ReportPeriod) || 'week',
  )
  const report = ref<ReportResponse | null>(null)
  const reviewStatus = ref('')

  // 日历详情
  const dayDetailDate = ref('')
  const dayDetail = ref<import('../types/api').DayResponse | null>(null)
  const daySegments = ref<Segment[]>([])
  const dayDetailSequence = ref(0)
  const loadSequence = ref(0)

  const reportTitle = computed(() => {
    if (!report.value) return ''
    const start = report.value.start
    if (report.value.period === 'week') {
      const { end } = weekBounds(start)
      const startText = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(new Date(`${start}T00:00:00`))
      const endText = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(new Date(`${end}T00:00:00`))
      return `${startText} – ${endText}`
    }
    if (report.value.period === 'month') {
      const parsed = new Date(`${start}T00:00:00`)
      return `${parsed.getFullYear()} 年 ${parsed.getMonth() + 1} 月`
    }
    const parsed = new Date(`${start}T00:00:00`)
    return `${parsed.getFullYear()} 年第 ${Math.floor(parsed.getMonth() / 3) + 1} 季度`
  })

  function setPeriod(value: ReportPeriod) {
    period.value = value
    safeStorageSet(STORAGE.reportPeriod, value)
  }

  /** 期间锚点：复用 day store 的 date（平移旧实现 state.date 双视图复用） */
  function anchorDate(): string {
    return useDayStore().date
  }

  async function loadReport() {
    const sequence = ++loadSequence.value
    const data = await reportsApi.fetchReport(anchorDate(), period.value)
    if (sequence !== loadSequence.value) return
    report.value = data
    ensureDayDetailDate()
    await loadDayDetail()
  }

  function shiftAnchor(direction: number) {
    const dayStore = useDayStore()
    dayStore.setDate(shiftPeriod(dayStore.date, period.value, direction))
  }

  /** 确保日历详情锚定在当前期间内（平移 ensureDayDetailDate） */
  function ensureDayDetailDate() {
    if (!report.value) return
    const { start, end } = report.value
    const today = localDateString(new Date())
    const fallback = today >= start && today <= end ? today : start
    if (!dayDetailDate.value || dayDetailDate.value < start || dayDetailDate.value > end) {
      dayDetailDate.value = fallback
    }
  }

  function setDayDetailDate(value: string) {
    if (!report.value) return
    const { start, end } = report.value
    dayDetailDate.value = value < start ? start : value > end ? end : value
    void loadDayDetail()
  }

  async function loadDayDetail() {
    if (!dayDetailDate.value) return
    const sequence = ++dayDetailSequence.value
    const { start, end } = weekBounds(dayDetailDate.value)
    const [detail, segments] = await Promise.all([
      // 复用 /api/day 拿详情（含 entries），平移旧实现 loadDayDetail
      import('../api/day').then((m) => m.fetchDay(dayDetailDate.value)),
      timersApi.fetchSegments(start, end),
    ])
    if (sequence !== dayDetailSequence.value) return
    dayDetail.value = detail
    daySegments.value = segments
  }

  /** 日历网格布局：把 segment 分配到 7 天 × 24 小时的车道（平移 layoutDayBlocks 的数据部分） */
  interface CalBlock {
    segment: Segment
    dayIndex: number
    topPercent: number
    heightPercent: number
    lane: number
    laneCount: number
  }

  const calBlocks = computed<CalBlock[]>(() => {
    const segments = daySegments.value
    if (!report.value || !segments.length) return []
    const { start } = report.value
    const blocks: CalBlock[] = []
    // 每条 segment 独占起点所在列；车道按重叠分组
    const lanesByDay = new Map<string, { segment: Segment; lane: number }[]>()
    const sorted = [...segments].sort((a, b) => a.start_at.localeCompare(b.start_at))
    sorted.forEach((segment) => {
      const day = segment.plan_date || segment.start_at.slice(0, 10)
      const dayList = lanesByDay.get(day) ?? []
      // 找第一个不重叠车道
      let lane = 0
      for (;;) {
        const conflict = dayList.some(
          (item) => item.lane === lane && overlaps(item.segment, segment),
        )
        if (!conflict) break
        lane += 1
      }
      dayList.push({ segment, lane })
      lanesByDay.set(day, dayList)
    })
    const laneCounts = new Map<string, number>()
    lanesByDay.forEach((list, day) => {
      laneCounts.set(day, list.reduce((max, item) => Math.max(max, item.lane + 1), 1))
    })
    lanesByDay.forEach((list, day) => {
      const dayIndex = Math.round((new Date(`${day}T00:00:00`).getTime() - new Date(`${start}T00:00:00`).getTime()) / 86_400_000)
      if (dayIndex < 0 || dayIndex > 6) return
      list.forEach(({ segment, lane }) => {
        const startDate = new Date(segment.start_at)
        const endDate = segment.end_at ? new Date(segment.end_at) : new Date(useTimerStore().now)
        const startMinutes = startDate.getHours() * 60 + startDate.getMinutes()
        const durationMinutes = Math.max(5, (endDate.getTime() - startDate.getTime()) / 60_000)
        blocks.push({
          segment,
          dayIndex,
          topPercent: (startMinutes / 1440) * 100,
          heightPercent: Math.min(100 - (startMinutes / 1440) * 100, (durationMinutes / 1440) * 100),
          lane,
          laneCount: laneCounts.get(day) ?? 1,
        })
      })
    })
    return blocks
  })

  function overlaps(a: Segment, b: Segment): boolean {
    const aStart = new Date(a.start_at).getTime()
    const aEnd = a.end_at ? new Date(a.end_at).getTime() : Date.now()
    const bStart = new Date(b.start_at).getTime()
    const bEnd = b.end_at ? new Date(b.end_at).getTime() : Date.now()
    return aStart < bEnd && bStart < aEnd
  }

  async function saveReview(content: string) {
    if (!report.value) return
    reviewStatus.value = ''
    const saved = await reportsApi.saveReview(period.value, report.value.start, content)
    if (report.value) report.value.review = saved.content
    reviewStatus.value = '已保存'
    window.setTimeout(() => {
      reviewStatus.value = ''
    }, 1500)
  }

  return {
    period,
    report,
    reviewStatus,
    dayDetailDate,
    dayDetail,
    daySegments,
    calBlocks,
    reportTitle,
    setPeriod,
    loadReport,
    shiftAnchor,
    ensureDayDetailDate,
    setDayDetailDate,
    loadDayDetail,
    saveReview,
  }
})
