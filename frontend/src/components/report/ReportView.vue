<script setup lang="ts">
import { computed } from 'vue'
import type { ReportPeriod } from '../../types/api'
import { useDayStore } from '../../stores/day'
import { useReportStore } from '../../stores/report'
import { todayString } from '../../utils/date'
import { formatHours, formatMinutes } from '../../utils/format'
import DayDetailPanel from './DayDetailPanel.vue'
import RoutineBoard from './RoutineBoard.vue'
import HeatmapPanel from './HeatmapPanel.vue'
import InsightsPanel from './InsightsPanel.vue'
import ProjectStats from './ProjectStats.vue'
import FocusStatsPanel from './FocusStatsPanel.vue'
import WeekReviewPanel from './WeekReviewPanel.vue'

const reportStore = useReportStore()
const dayStore = useDayStore()

const periodOptions: { value: ReportPeriod; label: string }[] = [
  { value: 'week', label: '周' },
  { value: 'month', label: '月' },
  { value: 'quarter', label: '季度' },
]

const periodName = computed(
  () => ({ week: '本周', month: '本月', quarter: '本季度' })[reportStore.period],
)

const totals = computed(() => {
  const days = reportStore.report?.days ?? []
  const planned = days.reduce((sum, day) => sum + Number(day.estimate_minutes || 0), 0)
  const actualSeconds = days.reduce((sum, day) => sum + Number(day.actual_seconds || 0), 0)
  const completed = days.reduce((sum, day) => sum + Number(day.completed_count || 0), 0)
  const total = days.reduce((sum, day) => sum + Number(day.total_count || 0), 0)
  const rate = total ? Math.round((completed / total) * 100) : 0
  const variance = Math.round(actualSeconds / 60 - planned)
  const varianceLabel =
    actualSeconds === 0 && planned === 0
      ? '—'
      : variance === 0
        ? '刚好'
        : `${variance > 0 ? '+' : '−'}${formatMinutes(Math.abs(variance))}`
  return {
    plannedLabel: formatHours(planned),
    actualLabel: formatHours(actualSeconds / 60),
    completed,
    total,
    rate,
    varianceLabel,
  }
})

function choosePeriod(period: ReportPeriod) {
  reportStore.setPeriod(period)
  void reportStore.loadReport()
}

function shiftPeriod(direction: number) {
  reportStore.shiftAnchor(direction)
  void reportStore.loadReport()
}

function backToCurrent() {
  dayStore.setDate(todayString())
  void reportStore.loadReport()
}
</script>

<template>
  <section class="view">
    <div class="view-pin">
      <div class="view-toolbar">
        <div>
          <p class="eyebrow">从记录中找规律</p>
          <h1>{{ reportStore.reportTitle }}</h1>
        </div>
        <div class="report-controls">
          <div class="period-switch" aria-label="复盘周期">
            <button
              v-for="option in periodOptions"
              :key="option.value"
              type="button"
              :data-period="option.value"
              :class="{ 'is-active': reportStore.period === option.value }"
              @click="choosePeriod(option.value)"
            >
              {{ option.label }}
            </button>
          </div>
          <div class="date-controls">
            <button type="button" class="icon-button" aria-label="上一个周期" @click="shiftPeriod(-1)">←</button>
            <button type="button" class="button subtle compact" @click="backToCurrent">当前周期</button>
            <button type="button" class="icon-button" aria-label="下一个周期" @click="shiftPeriod(1)">→</button>
          </div>
        </div>
      </div>

      <section class="summary-grid week-summary">
        <article class="summary-card accent">
          <span>{{ periodName }}计划</span>
          <strong>{{ totals.plannedLabel }}</strong>
          <small>每天预估相加</small>
        </article>
        <article class="summary-card">
          <span>有效工作</span>
          <strong>{{ totals.actualLabel }}</strong>
          <small>所有计时段相加</small>
        </article>
        <article class="summary-card">
          <span>完成安排</span>
          <strong>{{ totals.completed }} / {{ totals.total }}</strong>
          <small>完成率 {{ totals.rate }}%</small>
        </article>
        <article class="summary-card">
          <span>预估偏差</span>
          <strong>{{ totals.varianceLabel }}</strong>
          <small>实际与计划的差值</small>
        </article>
      </section>
    </div>

    <div class="week-layout">
      <DayDetailPanel />
      <RoutineBoard />
      <HeatmapPanel />
      <InsightsPanel />
      <ProjectStats />
      <FocusStatsPanel />
      <WeekReviewPanel />
    </div>
  </section>
</template>

<style scoped>
.report-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.period-switch {
  display: flex;
  gap: 3px;
  padding: 4px;
  border-radius: 10px;
  background: #e9eeeb;
}

.period-switch button {
  min-width: 48px;
  height: 32px;
  border: 0;
  border-radius: 7px;
  color: var(--muted);
  background: transparent;
  font-weight: 700;
}

.period-switch button.is-active {
  color: var(--green-dark);
  background: #fff;
  box-shadow: 0 2px 8px rgba(34, 51, 43, 0.08);
}

.date-controls {
  display: flex;
  align-items: center;
  gap: 7px;
}

.week-layout {
  display: grid;
  grid-template-columns: 1.35fr 0.65fr;
  gap: 18px;
}

@media (max-width: 900px) {
  .week-layout {
    grid-template-columns: 1fr;
  }
}
</style>
