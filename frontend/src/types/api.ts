// API 类型契约 —— 与 docs/refactor/api-catalog.md 保持一致（手写声明，不做运行时校验）

// ---------- 通用 ----------
export interface ApiErrorBody {
  error: string
}

export interface DayImages {
  id: number
  width: number | null
  height: number | null
}

export interface ReasonOption {
  value: string
  label: string
}

// ---------- 任务 entries ----------
export type EntryOutcome = 'planned' | 'completed' | 'carry' | 'reschedule' | 'abandoned' | ''

export interface Entry {
  id: number
  plan_date: string
  title: string
  project_name: string | null
  estimate_minutes: number
  planned_start: string | null
  sort_order: number
  outcome: EntryOutcome | null
  unfinished_reason: string | null
  reason_note: string | null
  target_date: string | null
  thread_id: number | null
  task_id: number | null
  parent_id: number | null
  definition: string | null
  task_status: string | null
  thread_title: string | null
  actual_seconds: number
  is_running: boolean
  has_children: boolean
}

export interface ProjectOption {
  id: number
  name: string
  color: string | null
}

// ---------- 主线 threads ----------
export interface ThreadDay {
  id: number
  title: string
  done_when: string
  step: string | null
  status: 'active' | 'paused' | 'done'
  featured: boolean
  project_name: string | null
  estimate_minutes: number
  steps: ThreadStep[]
  actual_seconds: number
  is_running: boolean
  created_at: string
}

export interface ThreadStep {
  id: number
  step: string
  done: boolean
  sort_order: number
}

// ---------- 必做 routines ----------
export interface RoutineDay {
  id: number
  title: string
  note: string | null
  estimate_minutes: number
  color: string
  active: boolean
  completed: boolean
  locked: boolean
  feedback_count: number
  is_running: boolean
  actual_seconds: number
}

export interface PublicRoutine {
  id: number
  title: string
  note: string | null
  estimate_minutes: number
  color: string
  created_on: string
  active: boolean
  completed: boolean
  locked: boolean
  feedback_count: number
}

export interface RoutineChallenge {
  id: number
  expires_at: string
  questions: { prompt: string }[]
}

// ---------- 计时 timers / 工作记录 segments ----------
export interface ActiveTimer {
  entry_id: number | null
  routine_id: number | null
  title: string
  mode: 'open' | 'focus'
  start_at: string
  target_seconds: number | null
  plan_date?: string | null
  plan_entry_id?: number | null
  entry?: Entry | null
  routine?: RoutineDay | null
}

export interface TimerStartResult {
  started: Entry | null
  stopped_entry_id: number | null
  stopped_routine_id?: number | null
  already_running: boolean
  mode?: 'open' | 'focus'
  target_seconds?: number
}

export interface TimerStopResult {
  stopped: boolean
  entry_id: number | null
  duration_seconds?: number
  mode?: 'open' | 'focus'
  focus_completed?: boolean
  routine_id?: number | null
}

export interface Segment {
  id: number
  start_at: string
  end_at: string | null
  duration_seconds: number
  mode: 'open' | 'focus'
  focus_completed: boolean
  entry_id: number | null
  plan_date: string | null
  estimate_minutes: number | null
  planned_start: string | null
  title: string | null
  project_name: string | null
}

// ---------- 日记 day ----------
export interface DayRow {
  plan_date: string
  focus: string
  reflection: string
  mood: number | null
  closed_at: string | null
  updated_at: string | null
  images: DayImages[]
}

export interface DayResponse {
  date: string
  day: DayRow
  entries: Entry[]
  projects: ProjectOption[]
  active_timer: ActiveTimer | null
  segments: Segment[]
  reasons: ReasonOption[]
  routines: RoutineDay[]
  threads: ThreadDay[]
}

export interface CloseDecision {
  entry_id: number
  action: 'completed' | 'carry' | 'reschedule' | 'abandoned'
  reason?: string
  note?: string
  target_date?: string
  next_estimate_minutes?: number
  next_step?: string
}

// ---------- 感悟 memos ----------
export interface MemoImage {
  id: number
  width: number | null
  height: number | null
}

export interface Memo {
  id: number | string // kind=daily 时 id 为日期字符串
  kind: 'memo' | 'daily'
  memo_date: string
  content: string
  content_format?: string
  tags: string
  pinned: boolean
  note_title: string | null
  note_link: string | null
  source_entry_id: number | null
  source_title: string | null
  source_estimate_minutes: number | null
  source_actual_seconds: number | null
  source_plan_date: string | null
  source_kind: '' | 'task' | 'routine' | 'thread'
  source_routine_id: number | null
  source_thread_id: number | null
  source_task_id: number | null
  source_thread_title?: string | null
  created_at: string
  updated_at: string
  images: MemoImage[]
  read_count: number
  last_read_at: string | null
  read_today: boolean
}

export interface MemoSource {
  kind: 'thread' | 'routine'
  id: number
  title: string
  count: number
  featured: boolean
  active: boolean
}

export interface MemoTemplate {
  id: number
  name: string
  content: string
  updated_at: string
}

export interface MemoReadResult {
  kind: 'memo' | 'daily'
  id: number | string
  read_count: number
  last_read_at: string | null
  read_today: boolean
  counted: boolean
}

// ---------- 报告 reports ----------
export type ReportPeriod = 'week' | 'month' | 'quarter'

export interface ReportDay {
  plan_date: string
  estimate_minutes: number
  actual_seconds: number
  completed_count: number
  total_count: number
  focus_count: number
}

export interface ReportProject {
  project_name: string | null
  estimate_minutes: number
  actual_seconds: number
  completed_count: number
  total_count: number
}

export interface CarryoverItem {
  task_id: number
  title: string
  carry_count: number
  latest_target_date: string | null
}

export interface ReportFocus {
  segment_count: number
  completed_count: number
  actual_seconds: number
  longest_streak: number
}

export interface ReportInsight {
  tone: 'warning' | 'positive' | 'info'
  title: string
  body: string
}

export interface RoutineReportDay {
  date: string
  status: 'done' | 'missed' | 'future' | 'unset'
}

export interface RoutineReport {
  id: number
  title: string
  note: string | null
  estimate_minutes: number
  color: string
  active: boolean
  completed_count: number
  applicable_count: number
  streak: number
  days: RoutineReportDay[]
}

export interface ReportResponse {
  period: ReportPeriod
  start: string
  end: string
  days: ReportDay[]
  reasons: { reason: string; count: number; label: string }[]
  projects: ReportProject[]
  carryovers: CarryoverItem[]
  focus: ReportFocus
  insights: ReportInsight[]
  review: string
  routines: RoutineReport[]
}

// ---------- 提醒 reminders ----------
export interface Reminder {
  id: number
  message: string
  remind_at: string
  status: 'pending' | 'done'
}

// ---------- 设置 settings ----------
export interface Profile {
  display_name: string
  avatar_data: string | null
  focus_minutes: number
  break_minutes: number
}

export interface SettingsResponse {
  profile: Profile
  routines: PublicRoutine[]
}

// ---------- 图片 images ----------
export interface ImageMeta {
  id: number
  width: number | null
  height: number | null
  owner_type: 'day' | 'memo'
  owner_key: string
}

// ---------- AI 流式（预留） ----------
export interface ChatStreamEvent {
  delta: string
  done: boolean
  error: string | null
}

export interface ImageStreamEvent {
  step: string
  progress: number
  image_url: string | null
  done: boolean
  error: string | null
}
