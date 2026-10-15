<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Segment } from '../../types/api'
import { useReportStore } from '../../stores/report'
import { useTimerStore } from '../../stores/timer'
import { localDateString, parseLocalDate, shiftDate, weekBounds } from '../../utils/date'
import { formatMinutes, formatShortClock } from '../../utils/format'
import SegmentPopover from './SegmentPopover.vue'
import SegmentDialog from '../dialogs/SegmentDialog.vue'

function getFullscreenElement(): Element | null {
  const doc = document as any
  return (
    document.fullscreenElement ??
    doc.webkitFullscreenElement ??
    doc.msFullscreenElement ??
    null
  )
}

async function enterFullscreen(el: HTMLElement) {
  const anyEl = el as any
  if (el.requestFullscreen) {
    await el.requestFullscreen()
  } else if (anyEl.webkitRequestFullscreen) {
    await anyEl.webkitRequestFullscreen()
  } else if (anyEl.msRequestFullscreen) {
    await anyEl.msRequestFullscreen()
  }
}

async function exitFullscreen() {
  const doc = document as any
  if (document.exitFullscreen) {
    await document.exitFullscreen()
  } else if (doc.webkitExitFullscreen) {
    await doc.webkitExitFullscreen()
  } else if (doc.msExitFullscreen) {
    await doc.msExitFullscreen()
  }
}

const reportStore = useReportStore()
const timerStore = useTimerStore()

// ---------- 布局：以 legacy layoutDayBlocks/segmentBounds 为准在本地实现 ----------
// report store 的 calBlocks 与本实现有出入（车道宽度按「全天最大车道数」而非
// 「当前块重叠簇的车道数」、缺少 22px 最小高度与边界钳制），故组件内本地计算。

const HOUR_HEIGHT = 48
const WEEKDAY = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const HOURS = Array.from({ length: 24 }, (_, hour) => hour)

interface LayoutItem {
  segment: Segment
  start: number
  end: number
  lane: number
  lanes: number
}

function minutesFromMidnight(value: string): number {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return 0
  return parsed.getHours() * 60 + parsed.getMinutes() + parsed.getSeconds() / 60
}

function segmentBounds(segment: Segment, nowMs: number) {
  const start = Math.max(0, Math.min(24 * 60, minutesFromMidnight(segment.start_at)))
  let end = segment.end_at
    ? minutesFromMidnight(segment.end_at)
    : start + Math.max(1, (nowMs - new Date(segment.start_at).getTime()) / 60000)
  if (end <= start) end = start + Math.max(1, Number(segment.duration_seconds || 60) / 60)
  end = Math.max(start + 1, Math.min(24 * 60, end))
  return { start, end }
}

function layoutDayBlocks(segments: Segment[], nowMs: number): LayoutItem[] {
  const items: LayoutItem[] = segments
    .map((segment) => {
      const bounds = segmentBounds(segment, nowMs)
      return { segment, start: bounds.start, end: bounds.end, lane: 0, lanes: 1 }
    })
    .sort((left, right) => left.start - right.start || left.end - right.end)
  const laneEnds: number[] = []
  items.forEach((item) => {
    let lane = laneEnds.findIndex((end) => end <= item.start + 0.01)
    if (lane < 0) {
      lane = laneEnds.length
      laneEnds.push(item.end)
    } else {
      laneEnds[lane] = item.end
    }
    item.lane = lane
  })
  items.forEach((item) => {
    const overlapping = items.filter(
      (other) => other.start < item.end - 0.01 && other.end > item.start + 0.01,
    )
    item.lanes = Math.max(1, ...overlapping.map((other) => other.lane + 1))
  })
  return items
}

// ---------- 周视图数据 ----------

const date = computed(() => reportStore.dayDetailDate)

const weekDays = computed(() => {
  if (!date.value) return []
  const { start } = weekBounds(date.value)
  return Array.from({ length: 7 }, (_, index) => shiftDate(start, index))
})

const today = computed(() => localDateString(new Date(timerStore.now)))

const heading = computed(() => {
  const current = date.value
  if (!current) return ''
  const label = new Intl.DateTimeFormat('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  }).format(parseLocalDate(current))
  if (current === today.value) return `今天 · ${label}`
  if (current === shiftDate(today.value, -1)) return `昨天 · ${label}`
  if (current === shiftDate(today.value, -2)) return `前天 · ${label}`
  return label
})

const summaryText = computed(() => {
  const selected = reportStore.daySegments.filter((segment) => segment.plan_date === date.value)
  const nowMs = timerStore.now
  const minutes = selected.reduce((sum, segment) => {
    if (segment.end_at) return sum + Number(segment.duration_seconds || 0) / 60
    return sum + Math.max(0, (nowMs - new Date(segment.start_at).getTime()) / 60000)
  }, 0)
  return selected.length
    ? `这一天 ${selected.length} 段计时 · 实际 ${formatMinutes(minutes)}`
    : '这一天还没有计时，空着的格子就是没记下的时间'
})

function blocksForDay(day: string): LayoutItem[] {
  return layoutDayBlocks(
    reportStore.daySegments.filter((segment) => segment.plan_date === day),
    timerStore.now,
  )
}

function blockHeight(item: LayoutItem): number {
  return Math.max(22, ((item.end - item.start) / 60) * HOUR_HEIGHT - 2)
}

function blockStyle(item: LayoutItem) {
  const top = (item.start / 60) * HOUR_HEIGHT
  const height = blockHeight(item)
  const width = 100 / item.lanes
  const left = item.lane * width
  return {
    top: `${top}px`,
    height: `${height}px`,
    left: `calc(${left}% + 2px)`,
    width: `calc(${width}% - 4px)`,
  }
}

function clockText(segment: Segment): string {
  return `${formatShortClock(segment.start_at)}–${formatShortClock(segment.end_at)}`
}

function indexWeekend(day: string): boolean {
  const dow = parseLocalDate(day).getDay()
  return dow === 0 || dow === 6
}

const nowLine = computed(() => {
  const moment = new Date(timerStore.now)
  const top = ((moment.getHours() * 60 + moment.getMinutes()) / 60) * HOUR_HEIGHT
  const label = `${String(moment.getHours()).padStart(2, '0')}:${String(moment.getMinutes()).padStart(2, '0')}`
  return { visible: weekDays.value.includes(today.value), top: `${top}px`, label }
})

// ---------- 日期导航 ----------

function onSelectDay(day: string) {
  if (day !== date.value) reportStore.setDayDetailDate(day)
}

function shiftDay(direction: number) {
  if (!date.value) return
  reportStore.setDayDetailDate(shiftDate(date.value, direction))
}

function gotoToday() {
  reportStore.setDayDetailDate(localDateString(new Date()))
}

function onDateChange(event: Event) {
  reportStore.setDayDetailDate((event.target as HTMLInputElement).value)
}

// ---------- segment popover / 调整对话框 ----------

interface PopoverState {
  segment: Segment
  anchor: { left: number; top: number; right: number }
}

const popover = ref<PopoverState | null>(null)
const editingSegment = ref<Segment | null>(null)

function openPopover(segment: Segment, event: MouseEvent) {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  popover.value = { segment, anchor: { left: rect.left, top: rect.top, right: rect.right } }
}

function closePopover() {
  popover.value = null
}

function openAdjust() {
  if (!popover.value) return
  editingSegment.value = popover.value.segment
  popover.value = null
}

function closeDialog() {
  editingSegment.value = null
}

watch(date, () => {
  popover.value = null
})

// ---------- 全屏 ----------

const panelRef = ref<HTMLElement | null>(null)
const isFullscreen = ref(false)

function updateFullscreenState() {
  const active = getFullscreenElement() === panelRef.value
  isFullscreen.value = active
  panelRef.value?.classList.toggle('is-fullscreen', active)
}

async function toggleFullscreen() {
  if (!panelRef.value) return
  try {
    if (isFullscreen.value) {
      await exitFullscreen()
    } else {
      panelRef.value.classList.add('is-fullscreen')
      await enterFullscreen(panelRef.value)
    }
  } catch {
    panelRef.value.classList.remove('is-fullscreen')
    // 浏览器可能不允许全屏，忽略错误
  }
}

onMounted(() => {
  document.addEventListener('fullscreenchange', updateFullscreenState)
  document.addEventListener('webkitfullscreenchange', updateFullscreenState)
  document.addEventListener('MSFullscreenChange', updateFullscreenState)
})

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', updateFullscreenState)
  document.removeEventListener('webkitfullscreenchange', updateFullscreenState)
  document.removeEventListener('MSFullscreenChange', updateFullscreenState)
})
</script>

<template>
  <section ref="panelRef" class="panel day-detail-panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">时间都去哪了</p>
        <h2>{{ heading }}</h2>
      </div>
      <div class="day-detail-controls">
        <button type="button" class="icon-button" aria-label="前一天" @click="shiftDay(-1)">←</button>
        <input type="date" :value="date" aria-label="查看哪一天" @change="onDateChange" />
        <button type="button" class="icon-button" aria-label="后一天" @click="shiftDay(1)">→</button>
        <button type="button" class="button subtle compact" @click="gotoToday">今天</button>
        <button type="button" class="button subtle compact fullscreen-toggle" @click="toggleFullscreen">
          {{ isFullscreen ? '退出全屏' : '全屏' }}
        </button>
      </div>
    </div>
    <p class="day-detail-summary">{{ summaryText }}</p>
    <div class="day-calendar">
      <div class="cal-sheet">
        <div class="cal-head">
          <div class="cal-gutter-head"></div>
          <button
            v-for="(day, index) in weekDays"
            :key="day"
            type="button"
            class="cal-day"
            :class="{ 'is-selected': day === date, 'is-today': day === today }"
            @click="onSelectDay(day)"
          >
            <span>{{ WEEKDAY[index] }}</span>
            <strong>{{ parseLocalDate(day).getDate() }}</strong>
          </button>
        </div>
        <div class="cal-scroll">
          <div class="cal-body">
            <div class="cal-hours">
              <div v-for="hour in HOURS" :key="hour" class="cal-hour-label">
                {{ String(hour).padStart(2, '0') }}:00
              </div>
            </div>
            <div class="cal-columns">
              <div v-if="nowLine.visible" class="cal-now" :style="{ top: nowLine.top }">
                <i></i>
                <span>{{ nowLine.label }}</span>
              </div>
              <div
                v-for="day in weekDays"
                :key="day"
                class="cal-col"
                :class="{ 'is-selected': day === date, 'is-weekend': indexWeekend(day) }"
              >
                <div v-for="hour in HOURS" :key="hour" class="cal-hour-slot"></div>
                <button
                  v-for="item in blocksForDay(day)"
                  :key="item.segment.id"
                  type="button"
                  class="cal-block"
                  :class="{
                    'is-focus': item.segment.mode === 'focus',
                    'is-open': popover?.segment.id === item.segment.id,
                  }"
                  :style="blockStyle(item)"
                  :title="`${item.segment.title} ${clockText(item.segment)}`"
                  @click="openPopover(item.segment, $event)"
                >
                  <strong>{{ item.segment.title }}</strong>
                  <span v-if="blockHeight(item) >= 38">{{ clockText(item.segment) }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <SegmentPopover
      v-if="popover"
      :segment="popover.segment"
      :anchor="popover.anchor"
      @close="closePopover"
      @adjust="openAdjust"
    />
    <SegmentDialog :open="editingSegment !== null" :segment="editingSegment" @close="closeDialog" />
  </section>
</template>

<style scoped>
.day-detail-panel {
  grid-column: 1 / -1;
}

.day-detail-controls {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 8px;
}

.day-detail-controls input {
  width: 148px;
  height: 36px;
}

.day-detail-summary {
  margin: 0 20px 8px;
  color: var(--muted);
  font-size: 13px;
}

.day-calendar {
  border-top: 1px solid var(--line);
  background: #fff;
}

.cal-sheet {
  min-width: 760px;
}

.cal-head {
  display: grid;
  grid-template-columns: 56px repeat(7, minmax(0, 1fr));
  position: sticky;
  top: calc(var(--header-height) + var(--bar-height, 0px));
  z-index: 4;
  background: #fff;
  border-bottom: 1px solid var(--line);
}

.cal-body {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  position: relative;
}

.cal-scroll {
  overflow: visible;
}

.cal-day {
  display: grid;
  gap: 2px;
  justify-items: center;
  padding: 8px 0 10px;
  border: 0;
  border-left: 1px solid #eef1ef;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
}

.cal-day strong {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 50%;
  color: var(--ink);
  font-size: 16px;
}

.cal-day.is-today strong {
  color: var(--green-dark);
}

.cal-day.is-selected strong {
  color: #fff;
  background: #3370ff;
}

.cal-hours {
  position: relative;
}

.cal-hour-label,
.cal-hour-slot {
  height: 48px;
}

.cal-hour-label {
  margin-top: -7px;
  padding-right: 8px;
  color: #8b948f;
  font-size: 11px;
  text-align: right;
}

.cal-hour-label:first-child {
  margin-top: 0;
  padding-top: 2px;
}

.cal-columns {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  position: relative;
  min-width: 0;
}

.cal-col {
  position: relative;
  padding-bottom: 28px;
  border-left: 1px solid #eef1ef;
  background:
    repeating-linear-gradient(
      to bottom,
      transparent 0,
      transparent 47px,
      #e7ece9 47px,
      #e7ece9 48px
    );
}

.cal-col.is-weekend {
  background-color: #fafafa;
}

.cal-col.is-selected {
  background-color: #f7f8fa;
}

.cal-block {
  position: absolute;
  z-index: 1;
  overflow: hidden;
  padding: 1px 6px;
  border: 0;
  border-radius: 2px;
  color: #133c9a;
  background: #e1eaff;
  box-shadow: none;
  text-align: left;
  cursor: pointer;
}

.cal-block.is-focus {
  color: #3c348b;
  background: #ecebff;
}

.cal-block:hover,
.cal-block.is-open {
  background: #c9daff;
}

.cal-block.is-focus:hover,
.cal-block.is-focus.is-open {
  background: #dddcfb;
}

.cal-block:focus-visible {
  outline: 2px solid #3370ff;
  outline-offset: 1px;
}

.cal-block strong,
.cal-block span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cal-block strong {
  font-size: 12px;
  font-weight: 650;
}

.cal-block span {
  color: inherit;
  font-size: 11px;
  opacity: 0.82;
}

.cal-now {
  position: absolute;
  right: 0;
  left: 0;
  z-index: 2;
  height: 0;
  border-top: 2px solid #d64545;
  pointer-events: none;
}

.cal-now i {
  position: absolute;
  top: -5px;
  left: -4px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d64545;
}

.cal-now span {
  position: absolute;
  top: -9px;
  left: 8px;
  color: #d64545;
  font-size: 11px;
  font-weight: 700;
  background: #fff;
}

.day-detail-panel.is-fullscreen {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  border-radius: 0;
  border: 0;
}

.day-detail-panel.is-fullscreen .day-calendar {
  max-height: calc(100vh - 140px);
  overflow-y: auto;
}

.day-detail-panel.is-fullscreen .cal-head {
  top: 0;
}

.fullscreen-toggle {
  margin-left: 4px;
}
</style>
