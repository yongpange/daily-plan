<script setup lang="ts">
import { computed } from 'vue'
import type { ReportDay } from '../../types/api'
import { useReportStore } from '../../stores/report'
import { parseLocalDate } from '../../utils/date'
import { formatMinutes } from '../../utils/format'

const reportStore = useReportStore()

const days = computed(() => reportStore.report?.days ?? [])

/** 首格对齐到周一：占位空白格数量（平移 renderHeatmap） */
const placeholderCount = computed(() => {
  if (!days.value.length) return 0
  const day = parseLocalDate(days.value[0].plan_date).getDay()
  return day === 0 ? 6 : day - 1
})

function minutesOf(day: ReportDay): number {
  return Number(day.actual_seconds || 0) / 60
}

function levelOf(day: ReportDay): number {
  const minutes = minutesOf(day)
  return minutes === 0 ? 0 : minutes <= 30 ? 1 : minutes <= 90 ? 2 : minutes <= 180 ? 3 : 4
}

function titleOf(day: ReportDay): string {
  return `${day.plan_date} · ${formatMinutes(minutesOf(day))}`
}

const streakLabel = computed(
  () => `最长连续记录 ${reportStore.report?.focus.longest_streak || 0} 天`,
)
</script>

<template>
  <section class="panel heatmap-panel">
    <div class="panel-header compact-header">
      <div>
        <p class="eyebrow">专注习惯</p>
        <h2>有效工作热力图</h2>
      </div>
      <span class="autosave-label">{{ streakLabel }}</span>
    </div>
    <div class="focus-heatmap">
      <span
        v-for="index in placeholderCount"
        :key="`placeholder-${index}`"
        class="heat-cell"
        style="visibility: hidden"
      ></span>
      <span
        v-for="day in days"
        :key="day.plan_date"
        class="heat-cell"
        :data-level="levelOf(day)"
        :title="titleOf(day)"
      ></span>
    </div>
  </section>
</template>

<style scoped>
.heatmap-panel {
  grid-column: 1 / -1;
}

.autosave-label {
  color: #89938e;
  font-size: 10px;
}

.focus-heatmap {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 14px;
  grid-template-rows: repeat(7, 14px);
  gap: 4px;
  overflow-x: auto;
  min-height: 122px;
  padding: 5px 22px 23px;
}

.heat-cell {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  background: #edf0ee;
}

.heat-cell[data-level="1"] {
  background: #d6eadf;
}

.heat-cell[data-level="2"] {
  background: #9fcdb4;
}

.heat-cell[data-level="3"] {
  background: #5b9c77;
}

.heat-cell[data-level="4"] {
  background: var(--green-dark);
}
</style>
