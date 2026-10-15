<script setup lang="ts">
// 今日视图组装 —— 平移 index.html todayView + renderDay 的日期控制。
// 日期切换统一走 dayStore.setDate，watch date 触发 loadDay（带序号防竞态在 store 内）。
import { ref, watch } from 'vue'
import { useDayStore } from '../../stores/day'
import { useUiStore } from '../../stores/ui'
import { errorMessage } from '../../api/http'
import { shiftDate, todayString } from '../../utils/date'
import type { Segment } from '../../types/api'
import SummaryGrid from './SummaryGrid.vue'
import FocusCard from './FocusCard.vue'
import RoutineTodayPanel from './RoutineTodayPanel.vue'
import TaskPanel from './TaskPanel.vue'
import WorklogPanel from './WorklogPanel.vue'
import QuickMemoPanel from './QuickMemoPanel.vue'
import ShutdownPanel from './ShutdownPanel.vue'
import CloseDayDialog from '../dialogs/CloseDayDialog.vue'
import SegmentDialog from '../dialogs/SegmentDialog.vue'

const dayStore = useDayStore()
const ui = useUiStore()

watch(
  () => dayStore.date,
  () => {
    void dayStore.loadDay().catch((error) => ui.notify(errorMessage(error), true))
  },
)

function shiftDay(direction: number) {
  dayStore.setDate(shiftDate(dayStore.date, direction))
}

function pickDay(event: Event) {
  const value = (event.target as HTMLInputElement).value
  if (value) dayStore.setDate(value)
}

function backToday() {
  dayStore.setDate(todayString())
}

// 收工复盘对话框（由 shutdown-panel 打开）
const closeDayOpen = ref(false)

// 工作记录修正（SegmentDialog 保存后走 reportStore；今日视图这里补一次 loadDay 刷新）
const segmentOpen = ref(false)
const segmentTarget = ref<Segment | null>(null)

function openSegment(segment: Segment) {
  segmentTarget.value = segment
  segmentOpen.value = true
}

function onSegmentClose() {
  segmentOpen.value = false
  segmentTarget.value = null
  void dayStore.loadDay().catch(() => {})
}
</script>

<template>
  <section id="todayView" class="view">
    <div class="view-pin">
      <div class="view-toolbar">
        <div>
          <p id="dateEyebrow" class="eyebrow">{{ dayStore.dateEyebrow }}</p>
          <h1 id="dateTitle">{{ dayStore.dateTitle }}</h1>
        </div>
        <div class="date-controls">
          <button id="previousDay" class="icon-button" aria-label="前一天" @click="shiftDay(-1)">
            ←
          </button>
          <input
            id="dayPicker"
            type="date"
            aria-label="选择日期"
            :value="dayStore.date"
            @change="pickDay"
          />
          <button id="nextDay" class="icon-button" aria-label="后一天" @click="shiftDay(1)">
            →
          </button>
          <button
            id="backToday"
            class="button subtle compact"
            :disabled="dayStore.isToday"
            @click="backToday"
          >
            回到今天
          </button>
        </div>
      </div>

      <SummaryGrid />
      <FocusCard />
    </div>

    <div class="today-layout">
      <div class="primary-column">
        <RoutineTodayPanel />
        <TaskPanel />
        <WorklogPanel @edit-segment="openSegment" />
      </div>
      <aside class="side-column">
        <QuickMemoPanel />
        <ShutdownPanel @open-close="closeDayOpen = true" />
      </aside>
    </div>

    <CloseDayDialog :open="closeDayOpen" @close="closeDayOpen = false" />
    <SegmentDialog :open="segmentOpen" :segment="segmentTarget" @close="onSegmentClose" />
  </section>
</template>

<style scoped>
.primary-column {
  min-width: 0;
}
</style>
