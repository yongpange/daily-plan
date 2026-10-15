<script setup lang="ts">
// 今日工作日志 —— 平移 renderWorklog。进行中的 segment 秒数依赖 timerStore.now 每秒刷新。
// types/api.ts 的 Segment 没有 kind 字段（契约禁改），运行时 kind==='routine' 的记录
// 不提供“修正”入口，这里用本地扩展类型读取。
import { computed } from 'vue'
import { useDayStore } from '../../stores/day'
import { useTimerStore } from '../../stores/timer'
import { formatMinutes, formatShortClock } from '../../utils/format'
import type { Segment } from '../../types/api'

type SegmentExt = Segment & { kind?: string }

const emit = defineEmits<{ (e: 'edit-segment', segment: Segment): void }>()

const dayStore = useDayStore()
const timerStore = useTimerStore()

const segments = computed(() => (dayStore.day?.segments ?? []) as SegmentExt[])

function segmentSeconds(segment: SegmentExt): number {
  if (segment.end_at) return Number(segment.duration_seconds || 0)
  return Math.max(0, (timerStore.now - new Date(segment.start_at).getTime()) / 1000)
}

const totalLabel = computed(() =>
  formatMinutes(segments.value.reduce((sum, segment) => sum + segmentSeconds(segment), 0) / 60),
)
</script>

<template>
  <section class="panel worklog-panel">
    <div class="panel-header compact-header">
      <div>
        <p class="eyebrow">真实投入</p>
        <h2>今日工作日志</h2>
      </div>
      <span id="worklogTotal" class="autosave-label">{{ totalLabel }}</span>
    </div>
    <div id="worklogList" class="worklog-list">
      <div v-if="!segments.length" class="empty-inline">
        开始一次计时后，这里会按时间段留下工作日志
      </div>
      <article v-for="segment in segments" :key="segment.id" class="worklog-row" :data-segment-id="segment.id">
        <span class="worklog-icon" :class="{ 'is-focus': segment.mode === 'focus' }">
          {{ segment.mode === 'focus' ? '◎' : '▶' }}
        </span>
        <div class="worklog-main">
          <strong>{{ segment.title }}</strong>
          <span>
            {{ segment.project_name }} ·
            {{ segment.mode === 'focus' ? (segment.focus_completed ? '完整专注' : '专注段') : '自由计时' }}
          </span>
        </div>
        <div>
          <strong class="worklog-duration">{{ formatMinutes(segmentSeconds(segment) / 60) }}</strong>
          <span class="worklog-clock">
            {{ formatShortClock(segment.start_at) }}–{{ formatShortClock(segment.end_at) }}
          </span>
        </div>
        <button
          v-if="segment.end_at && segment.kind !== 'routine'"
          class="worklog-edit"
          aria-label="修正工作记录"
          @click="emit('edit-segment', segment)"
        >
          ···
        </button>
      </article>
    </div>
  </section>
</template>

<style scoped>
.autosave-label {
  color: #89938e;
  font-size: 10px;
}

.empty-inline {
  padding: 26px 8px;
  color: var(--muted);
  text-align: center;
  font-size: 12px;
}

.worklog-panel {
  margin-top: 18px;
}

.worklog-list {
  padding: 5px 20px 18px;
}

.worklog-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 11px;
  padding: 11px 0;
  border-bottom: 1px solid var(--line);
}

.worklog-row:last-child {
  border-bottom: 0;
}

.worklog-icon {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border-radius: 9px;
  color: var(--green);
  background: var(--green-soft);
}

.worklog-icon.is-focus {
  color: var(--purple);
  background: #f0edf9;
}

.worklog-main {
  min-width: 0;
}

.worklog-main strong,
.worklog-main span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.worklog-main span,
.worklog-clock {
  margin-top: 3px;
  color: var(--muted);
  font-size: 10px;
}

.worklog-duration {
  font-variant-numeric: tabular-nums;
  font-weight: 750;
}

.worklog-edit {
  width: 29px;
  height: 29px;
  border: 0;
  border-radius: 8px;
  color: var(--muted);
  background: var(--soft);
}
</style>
