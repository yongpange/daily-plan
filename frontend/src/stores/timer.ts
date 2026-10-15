import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import * as timerApi from '../api/timers'
import { fetchDay } from '../api/day'
import type { ActiveTimer } from '../types/api'
import { formatClock, formatMinutes } from '../utils/format'
import { safeStorageGet, safeStorageRemove, safeStorageSet, STORAGE } from '../utils/storage'
import router from '../router'
import { useUiStore, playTone } from './ui'

let tickHandle: number | undefined
let finishingFocus = false

export const useTimerStore = defineStore('timer', () => {
  const ui = useUiStore()

  /** 全局秒级时钟：所有倒计时/正计时 computed 依赖它 */
  const now = ref(Date.now())
  const activeTimer = ref<ActiveTimer | null>(null)
  /** loadDay 完成时刻，liveSeconds 的计算基准 */
  const syncedAt = ref(Date.now())
  const breakUntil = ref(Number(safeStorageGet(STORAGE.breakUntil) || 0))

  const isRunning = computed(() => activeTimer.value !== null)
  const breakRemaining = computed(() => Math.max(0, breakUntil.value - now.value))
  const isBreakActive = computed(() => breakRemaining.value > 0)

  const runningElapsed = computed(() => {
    const active = activeTimer.value
    if (!active) return 0
    return Math.max(0, (now.value - new Date(active.start_at).getTime()) / 1000)
  })

  const runningIsFocus = computed(
    () => activeTimer.value?.mode === 'focus' && Boolean(activeTimer.value?.target_seconds),
  )

  const runningDisplayTime = computed(() =>
    runningIsFocus.value
      ? formatClock(Math.max(0, Number(activeTimer.value?.target_seconds) - runningElapsed.value))
      : formatClock(runningElapsed.value),
  )

  const runningProgressPercent = computed(() => {
    if (!runningIsFocus.value) return 0
    return Math.min(100, (runningElapsed.value / Number(activeTimer.value?.target_seconds)) * 100)
  })

  function startTicking() {
    if (tickHandle !== undefined) return
    tickHandle = window.setInterval(() => {
      now.value = Date.now()
      // 专注倒计时到点 → 自动结束（平移 updateLiveTimers 里的 finishFocusTimer）
      const active = activeTimer.value
      if (active && active.mode === 'focus' && active.target_seconds && !finishingFocus) {
        const remaining = Number(active.target_seconds) - (now.value - new Date(active.start_at).getTime()) / 1000
        if (remaining <= 0) void finishFocusTimer()
      }
      // 休息倒计时到点
      if (breakUntil.value) {
        const remaining = breakUntil.value - now.value
        if (remaining <= 0) {
          stopBreak()
          playTone()
          ui.notify('休息结束，可以开始下一段工作')
        }
      }
    }, 1000)
  }

  function stopTicking() {
    window.clearInterval(tickHandle)
    tickHandle = undefined
  }

  /** 后端 active_timer 字段是 start_at/plan_entry_id，统一映射到 start_at/entry_id */
  function normalizeTimer(timer: ActiveTimer | null): ActiveTimer | null {
    if (!timer) return null
    return {
      ...timer,
      entry_id: timer.entry_id ?? timer.plan_entry_id ?? null,
      start_at: timer.start_at,
    }
  }

  function setActiveTimer(timer: ActiveTimer | null) {
    const normalized = normalizeTimer(timer)
    activeTimer.value = normalized
    if (!normalized) {
      safeStorageRemove(STORAGE.timer)
      return
    }
    safeStorageSet(
      STORAGE.timer,
      JSON.stringify({
        entryId: normalized.entry_id,
        title: normalized.title,
        startAt: normalized.start_at,
        mode: normalized.mode,
        targetSeconds: normalized.target_seconds,
      }),
    )
  }

  interface StartOptions {
    entryId?: number
    routineId?: number
    date?: string
    mode?: 'open' | 'focus'
    focusMinutes?: number
  }

  async function startTimer(options: StartOptions) {
    stopBreak()
    const result = await timerApi.startTimer(
      options.routineId
        ? { routine_id: options.routineId, date: options.date ?? '', mode: 'open' }
        : { entry_id: options.entryId ?? 0, mode: options.mode ?? 'open', focus_minutes: options.focusMinutes },
    )
    await refreshAfterTimerChange()
    ui.notify(
      result.stopped_entry_id || result.stopped_routine_id
        ? '已结束上一条计时，并开始新的计时'
        : options.mode === 'focus' && !options.routineId
          ? `开始 ${options.focusMinutes} 分钟专注`
          : '已经开始计时',
    )
  }

  interface StopOptions {
    entryId?: number | null
    routineId?: number
    targetReached?: boolean
  }

  async function stopTimer(options: StopOptions = {}) {
    const result = await timerApi.stopTimer(
      options.routineId
        ? { routine_id: options.routineId }
        : { entry_id: options.entryId ?? null, target_reached: options.targetReached ?? false },
    )
    setActiveTimer(null)
    if (result.focus_completed) {
      const breakMinutes = Number(safeStorageGet(STORAGE.breakMinutes) || 5)
      startBreak(breakMinutes)
      playTone()
    }
    await refreshAfterTimerChange()
    ui.notify(
      result.stopped
        ? result.focus_completed
          ? `完整专注 ${formatMinutes(Number(result.duration_seconds) / 60)}，现在休息一下`
          : `本次有效工作 ${formatMinutes(Number(result.duration_seconds) / 60)}`
        : '当前没有正在计时的任务',
    )
    return result
  }

  async function finishFocusTimer() {
    if (finishingFocus || !activeTimer.value) return
    finishingFocus = true
    try {
      await stopTimer({ entryId: activeTimer.value.entry_id, targetReached: true })
    } finally {
      finishingFocus = false
    }
  }

  /** 计时变化后按当前路由刷新相关数据（平移旧 view 分支逻辑） */
  async function refreshAfterTimerChange() {
    const route = router.currentRoute.value.name
    if (route === 'today') {
      const { useDayStore } = await import('./day')
      await useDayStore().loadDay()
    } else if (route === 'report') {
      const { useReportStore } = await import('./report')
      await useReportStore().loadReport()
    } else {
      await refreshGlobalTimer()
    }
  }

  async function refreshGlobalTimer() {
    const { useDayStore } = await import('./day')
    const data = await fetchDay(useDayStore().date)
    setActiveTimer(data.active_timer)
  }

  function startBreak(minutes: number) {
    breakUntil.value = Date.now() + Math.max(1, Number(minutes)) * 60_000
    safeStorageSet(STORAGE.breakUntil, breakUntil.value)
  }

  function stopBreak() {
    breakUntil.value = 0
    safeStorageRemove(STORAGE.breakUntil)
  }

  return {
    now,
    activeTimer,
    syncedAt,
    breakUntil,
    isRunning,
    breakRemaining,
    isBreakActive,
    runningElapsed,
    runningIsFocus,
    runningDisplayTime,
    runningProgressPercent,
    startTicking,
    stopTicking,
    setActiveTimer,
    startTimer,
    stopTimer,
    finishFocusTimer,
    refreshGlobalTimer,
    startBreak,
    stopBreak,
  }
})
