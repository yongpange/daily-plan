import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import * as dayApi from '../api/day'
import * as entriesApi from '../api/entries'
import * as threadsApi from '../api/threads'
import { fetchMemos } from '../api/memos'
import type { DayResponse, Entry, ThreadDay } from '../types/api'
import { localDateString, parseLocalDate, shiftDate } from '../utils/date'
import { formatMinutes } from '../utils/format'
import { safeStorageSet, STORAGE } from '../utils/storage'
import { useTimerStore } from './timer'
import { useMemoStore } from './memo'

let saveTimer: number | undefined

export const useDayStore = defineStore('day', () => {
  const date = ref(localDateString(new Date()))
  const day = ref<DayResponse | null>(null)
  const mood = ref<number | null>(null)
  const saveStatus = ref('')
  const loadSequence = ref(0)

  // 今日/复盘输入草稿（组件 v-model 绑定到这里，防抖保存）
  const focusDraft = ref('')
  const reflectionDraft = ref('')

  const isToday = computed(() => date.value === localDateString(new Date()))
  const todayRoutines = computed(() => day.value?.routines ?? [])
  const threads = computed(() => day.value?.threads ?? [])
  const activeThreads = computed(() => threads.value.filter((thread) => thread.status === 'active'))
  const isClosed = computed(() => Boolean(day.value?.day.closed_at))

  const dateTitle = computed(() => {
    if (isToday.value) return '今日计划'
    return new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(
      parseLocalDate(date.value),
    )
  })

  const dateEyebrow = computed(() => {
    const today = localDateString(new Date())
    if (date.value === today) return '今天'
    if (date.value === shiftDate(today, -1)) return '昨天'
    if (date.value === shiftDate(today, 1)) return '明天'
    return `${parseLocalDate(date.value).getFullYear()} 年`
  })

  function setDate(value: string) {
    date.value = value
    safeStorageSet(STORAGE.date, value)
  }

  function applyDay(data: DayResponse) {
    day.value = data
    mood.value = data.day.mood
    focusDraft.value = data.day.focus || ''
    reflectionDraft.value = data.day.reflection || ''
    const timer = useTimerStore()
    timer.setActiveTimer(data.active_timer)
    timer.syncedAt = Date.now()
  }

  async function loadDay() {
    const sequence = ++loadSequence.value
    safeStorageSet(STORAGE.date, date.value)
    const [data, memos] = await Promise.all([
      dayApi.fetchDay(date.value),
      fetchMemos({ date: date.value, limit: 30 }),
    ])
    if (sequence !== loadSequence.value) return
    applyDay(data)
    useMemoStore().todayMemos = memos
  }

  /** focus/reflection/mood 防抖保存（平移 scheduleDaySave 550ms） */
  function scheduleDaySave() {
    saveStatus.value = ''
    window.clearTimeout(saveTimer)
    saveTimer = window.setTimeout(async () => {
      try {
        const row = await dayApi.saveDay({
          date: date.value,
          focus: focusDraft.value,
          reflection: reflectionDraft.value,
          mood: mood.value,
        })
        if (day.value) day.value.day = { ...day.value.day, ...row }
        saveStatus.value = '已自动保存'
        window.setTimeout(() => {
          saveStatus.value = ''
        }, 1500)
      } catch {
        saveStatus.value = ''
      }
    }, 550)
  }

  function setMood(value: number | null) {
    mood.value = value
    scheduleDaySave()
  }

  // ---------- 任务树派生（平移 entriesInTreeOrder 等） ----------

  const entries = computed(() => day.value?.entries ?? [])

  /** 按 parent 关系排成渲染顺序：顶层（含主线步骤）保持原序，子任务紧随父任务 */
  function entriesInTreeOrder(list: Entry[]): Entry[] {
    const byParent = new Map<number | null, Entry[]>()
    list.forEach((entry) => {
      const key = entry.parent_id
      if (!byParent.has(key)) byParent.set(key, [])
      byParent.get(key)!.push(entry)
    })
    const ordered: Entry[] = []
    const append = (entry: Entry) => {
      ordered.push(entry)
      for (const child of byParent.get(entry.task_id) ?? []) append(child)
    }
    for (const entry of byParent.get(null) ?? []) append(entry)
    return ordered
  }

  const treeEntries = computed(() => entriesInTreeOrder(entries.value))

  /** entry → 子任务（按 task_id 关联 parent_id，平移 entriesUnderTask） */
  function entriesUnderTask(list: Entry[], entry: Entry): Entry[] {
    return list.filter((candidate) => candidate.parent_id === entry.task_id)
  }

  function depthOf(list: Entry[], entry: Entry): number {
    let depth = 0
    let current = entry
    while (current.parent_id != null) {
      const parent = list.find((candidate) => candidate.task_id === current.parent_id)
      if (!parent) break
      depth += 1
      current = parent
    }
    return depth
  }

  // ---------- 计时聚合（依赖 timer.now 每秒刷新） ----------

  function liveSeconds(entry: Entry): number {
    const timer = useTimerStore()
    const base = Number(entry.actual_seconds) || 0
    if (!entry.is_running) return base
    return base + Math.max(0, Math.floor((timer.now - timer.syncedAt) / 1000))
  }

  function aggregateSeconds(entry: Entry): number {
    const list = entries.value
    if (!day.value) return liveSeconds(entry)
    const children = list.filter((candidate) => candidate.parent_id === entry.task_id)
    return liveSeconds(entry) + children.reduce((sum, child) => sum + aggregateSeconds(child), 0)
  }

  // ---------- 摘要统计（平移 renderSummary） ----------

  const summary = computed(() => {
    const list = entries.value
    const planned = list.reduce((sum, entry) => sum + (Number(entry.estimate_minutes) || 0), 0)
    const plannedTaskCount = list.filter((entry) => entry.thread_id == null).length
    const actualSeconds = list.reduce((sum, entry) => sum + aggregateSeconds(entry), 0)
    const completed = list.filter((entry) => entry.outcome === 'completed').length
    const total = list.filter((entry) => entry.task_status !== 'done').length || list.length
    const completionPercent = total ? Math.round((completed / total) * 100) : 0
    const varianceMinutes = actualSeconds / 60 - planned
    return {
      plannedMinutes: planned,
      plannedLabel: `${formatMinutes(planned)} · ${plannedTaskCount} 项`,
      actualLabel: formatMinutes(actualSeconds / 60),
      completionPercent,
      completedLabel: `${completed} / ${total}`,
      varianceLabel: `${varianceMinutes >= 0 ? '+' : '−'}${formatMinutes(Math.abs(varianceMinutes))}`,
      varianceHint: varianceMinutes > 30 ? '比计划慢了一些' : varianceMinutes < -30 ? '比预估更快' : '',
    }
  })

  // ---------- 任务操作 ----------

  interface CreateTaskPayload {
    title: string
    project_name?: string
    estimate_minutes?: number
    planned_start?: string
    parent_entry_id?: number
  }

  async function createTask(payload: CreateTaskPayload) {
    await entriesApi.createEntry({ date: date.value, ...payload })
    await loadDay()
  }

  /** 仅今天及以前可以标完成。返回 false 表示这次没有改状态。 */
  async function toggleComplete(entry: Entry) {
    if (date.value > localDateString(new Date())) return false
    if ((entry.outcome ?? '') === 'completed') return false
    await entriesApi.updateEntry(entry.id, { outcome: 'completed' })
    await loadDay()
    return true
  }

  /** 把已完成改回未完成（outcome=planned，任务重新激活） */
  async function reopenTask(entry: Entry) {
    await entriesApi.updateEntry(entry.id, { outcome: 'planned' })
    await loadDay()
  }

  async function saveTaskEdit(
    entryId: number,
    payload: { title: string; project_name: string; estimate_minutes: number; planned_start: string; definition: string },
  ) {
    await entriesApi.updateEntry(entryId, payload)
    await loadDay()
  }

  async function deleteTask(entryId: number) {
    await entriesApi.deleteEntry(entryId)
    await loadDay()
  }

  async function moveTaskTo(entryId: number, targetDate: string) {
    const result = await entriesApi.moveEntry(entryId, targetDate)
    await loadDay()
    return result
  }

  // ---------- 主线操作 ----------

  async function submitThread(payload: { title: string; done_when: string; step: string; project_name?: string; estimate_minutes?: number }) {
    const data = await threadsApi.createThread({ date: date.value, ...payload })
    applyDay(data)
  }

  async function submitThreadStep(threadId: number, step: string) {
    const data = await threadsApi.createThreadStep(threadId, { date: date.value, step })
    applyDay(data)
  }

  async function updateThread(threadId: number, payload: { status?: 'active' | 'paused' | 'done'; featured?: boolean }) {
    const data = await threadsApi.updateThread(threadId, { ...payload, date: date.value })
    applyDay(data)
  }

  /** 主线卡片辅助：最近一步文本 / 卡片展示线程 */
  function threadRecentText(thread: ThreadDay): string {
    const recent = [...(thread.steps || [])].reverse().find((stepItem) => stepItem.done)
    return recent?.step || thread.step || ''
  }

  return {
    date,
    day,
    mood,
    saveStatus,
    focusDraft,
    reflectionDraft,
    isToday,
    isClosed,
    todayRoutines,
    threads,
    activeThreads,
    entries,
    treeEntries,
    dateTitle,
    dateEyebrow,
    summary,
    setDate,
    loadDay,
    applyDay,
    scheduleDaySave,
    setMood,
    entriesInTreeOrder,
    entriesUnderTask,
    depthOf,
    liveSeconds,
    aggregateSeconds,
    createTask,
    toggleComplete,
    reopenTask,
    saveTaskEdit,
    deleteTask,
    moveTaskTo,
    submitThread,
    submitThreadStep,
    updateThread,
    threadRecentText,
  }
})
