<script setup lang="ts">
import { computed } from 'vue'
import type { RoutineReport } from '../../types/api'
import { useReportStore } from '../../stores/report'
import { parseLocalDate } from '../../utils/date'

const reportStore = useReportStore()

const routines = computed(() => reportStore.report?.routines ?? [])
const period = computed(() => reportStore.period)

const statusText: Record<string, string> = {
  done: '已完成',
  missed: '未完成',
  future: '未到',
  unset: '尚未开始',
}

function rateOf(routine: RoutineReport): number {
  return routine.applicable_count
    ? Math.round((routine.completed_count / routine.applicable_count) * 100)
    : 0
}

/** 横轴标签：周=星期几，月=日期数字，季度=仅周一标 M/D（平移 renderRoutineBoard） */
const axis = computed(() => {
  const sample = routines.value[0]?.days ?? []
  return sample.map((day) => {
    const date = parseLocalDate(day.date)
    if (period.value === 'week') {
      return ['一', '二', '三', '四', '五', '六', '日'][date.getDay() === 0 ? 6 : date.getDay() - 1]
    }
    if (period.value === 'month') return String(date.getDate())
    return date.getDay() === 1 ? `${date.getMonth() + 1}/${date.getDate()}` : ''
  })
})
</script>

<template>
  <section class="panel routine-report-panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">每日打卡</p>
        <h2>必做完成情况</h2>
      </div>
      <div class="routine-legend">
        <span><i data-status="done"></i>完成</span>
        <span><i data-status="missed"></i>未完成</span>
      </div>
    </div>
    <div v-if="!routines.length" class="routine-board">
      <div class="routine-empty">在设置里添加每日必做后，这里会按周、月、季度显示打卡。</div>
    </div>
    <div v-else class="routine-board" :data-period="period">
      <div class="routine-chart">
        <div class="routine-names">
          <span class="routine-axis-spacer"></span>
          <div v-for="routine in routines" :key="routine.id" class="routine-chart-name">
            <strong>{{ routine.title }}</strong>
            <span>
              {{ routine.completed_count }}/{{ routine.applicable_count }} · {{ rateOf(routine) }}% · 连续
              {{ routine.streak }} 天{{ routine.active ? '' : ' · 已停用' }}
            </span>
          </div>
        </div>
        <div class="routine-scroll">
          <div class="routine-axis">
            <span v-for="(label, index) in axis" :key="index">{{ label }}</span>
          </div>
          <div v-for="routine in routines" :key="routine.id" class="routine-cells">
            <span
              v-for="day in routine.days"
              :key="day.date"
              class="routine-cell"
              :data-status="day.status"
              :title="`${day.date} · ${statusText[day.status] || day.status}`"
            ></span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.routine-report-panel {
  grid-column: 1 / -1;
}

.routine-report-panel > .panel-header {
  padding-right: 28px;
  padding-left: 28px;
}

.routine-legend {
  display: flex;
  gap: 12px;
  color: var(--muted);
  font-size: 11px;
}

.routine-legend i,
.routine-cell {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 4px;
}

.routine-legend i[data-status="done"],
.routine-cell[data-status="done"] {
  border-color: transparent;
  background: #d64545;
}

.routine-legend i[data-status="missed"],
.routine-cell[data-status="missed"],
.routine-cell[data-status="future"],
.routine-cell[data-status="unset"] {
  border: 1px solid #e4e8e5;
  background: transparent;
}

.routine-board {
  padding: 4px 28px 24px;
}

.routine-empty {
  padding: 8px 2px 2px;
  color: var(--muted);
  line-height: 1.7;
}

.routine-chart {
  display: grid;
  grid-template-columns: minmax(140px, 220px) minmax(0, 1fr);
  gap: 12px;
  min-width: 0;
}

.routine-names,
.routine-scroll {
  display: grid;
  grid-template-rows: 18px;
  grid-auto-rows: 44px;
  align-content: start;
  min-width: 0;
}

.routine-scroll {
  overflow-x: auto;
  padding-bottom: 4px;
}

.routine-axis-spacer,
.routine-axis,
.routine-chart-name,
.routine-cells {
  min-height: 0;
  height: 100%;
}

.routine-chart-name strong,
.routine-chart-name span {
  display: block;
}

.routine-chart-name {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.routine-chart-name span,
.routine-axis {
  color: var(--muted);
  font-size: 11px;
}

.routine-cells,
.routine-axis {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(28px, 1fr);
  align-items: center;
  gap: 4px;
  width: 100%;
}

.routine-board[data-period="month"] .routine-cells,
.routine-board[data-period="month"] .routine-axis {
  width: max(100%, 620px);
}

.routine-board[data-period="quarter"] .routine-cells,
.routine-board[data-period="quarter"] .routine-axis {
  grid-auto-columns: 12px;
  width: max-content;
}

.routine-board[data-period="week"] .routine-cells,
.routine-board[data-period="week"] .routine-axis {
  grid-auto-columns: minmax(42px, 84px);
  justify-content: start;
  width: auto;
}

.routine-cell {
  width: auto;
  min-width: 0;
  height: 22px;
}

.routine-axis span {
  overflow: hidden;
  text-align: center;
  white-space: nowrap;
}
</style>
