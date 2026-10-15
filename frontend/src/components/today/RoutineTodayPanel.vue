<script setup lang="ts">
// 今日必做 —— 平移 renderTodayRoutines / toggleRoutine / startRoutineTimer / stopRoutineTimer。
// 实际秒数本地计算：RoutineDay 类型没有 running_started_at，改用 timerStore 的
// 全局 activeTimer（routine_id 匹配且正在计时则累加）。
import router from '../../router'
import { useDayStore } from '../../stores/day'
import { useRoutineStore } from '../../stores/routine'
import { useTimerStore } from '../../stores/timer'
import { useDialogStore } from '../../stores/dialogs'
import { useMemoStore } from '../../stores/memo'
import { formatMinutes } from '../../utils/format'
import { todayString } from '../../utils/date'
import type { RoutineDay } from '../../types/api'

const dayStore = useDayStore()
const routineStore = useRoutineStore()
const timerStore = useTimerStore()
const dialogsStore = useDialogStore()
const memoStore = useMemoStore()

const future = () => dayStore.date > todayString()

function liveRoutineSeconds(routine: RoutineDay): number {
  const base = Number(routine.actual_seconds) || 0
  const active = timerStore.activeTimer
  if (!routine.is_running || !active || active.routine_id !== routine.id) return base
  return base + Math.max(0, Math.floor((timerStore.now - new Date(active.start_at).getTime()) / 1000))
}

async function toggle(routine: RoutineDay) {
  const done = Boolean(routine.completed)
  await routineStore.toggleRoutine(routine.id, dayStore.date, !done)
  if (!done) {
    dialogsStore.openTaskNote({ kind: 'routine', routineId: routine.id, title: routine.title })
  }
}

function openAllFeedback(routine: RoutineDay) {
  memoStore.openMemoSource('routine', routine.id)
  void router.push({ name: 'memos' })
}
</script>

<template>
  <section class="panel routine-today-panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">每天都要做</p>
        <h2>今日必做</h2>
      </div>
      <span class="routine-lock-label">只能在设置中修改</span>
    </div>
    <div id="routineTodayList" class="routine-today-list">
      <div v-if="!dayStore.todayRoutines.length" class="routine-empty">
        还没有每天必做的事。
        <button type="button" @click="router.push({ name: 'settings' })">去设置里添加</button>
      </div>
      <article
        v-for="routine in dayStore.todayRoutines"
        :key="routine.id"
        class="routine-item"
        :class="{ 'is-done': routine.completed }"
        :style="{ '--routine': routine.color }"
      >
        <button
          class="routine-check"
          type="button"
          :disabled="future()"
          :aria-label="routine.completed ? '取消今天的打卡' : '完成今天的必做'"
          @click="toggle(routine)"
        >
          ✓
        </button>
        <div>
          <h3 class="routine-title">{{ routine.title }}</h3>
          <div class="routine-meta">
            <span>每日必做</span>
            <span v-if="routine.note">{{ routine.note }}</span>
            <span v-if="routine.estimate_minutes">预估 {{ formatMinutes(routine.estimate_minutes) }}</span>
            <span class="routine-actual" :data-routine-time="routine.id">
              实际 {{ formatMinutes(liveRoutineSeconds(routine) / 60) }}
            </span>
            <span>{{ future() ? '还没到这一天' : '首页不能修改' }}</span>
          </div>
          <div v-if="!future()" class="routine-feedback">
            <button
              v-if="routine.is_running"
              type="button"
              class="is-running"
              @click="routineStore.stopRoutineTimer(routine.id)"
            >
              ■ 结束计时
            </button>
            <button v-else type="button" @click="routineStore.startRoutineTimer(routine.id, dayStore.date)">
              ▶ 开始
            </button>
            <template v-if="routine.completed">
              <button
                type="button"
                @click="dialogsStore.openTaskNote({ kind: 'routine', routineId: routine.id, title: routine.title })"
              >
                写反馈
              </button>
              <button type="button" @click="openAllFeedback(routine)">
                全部反馈{{ routine.feedback_count ? ` · ${routine.feedback_count}` : '' }}
              </button>
            </template>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.routine-today-panel {
  border-color: #efd7a4;
  background:
    linear-gradient(180deg, rgba(255, 247, 232, 0.9), #fff 72px),
    var(--surface);
}

.routine-lock-label {
  color: #8a5a12;
  font-size: 12px;
}

.routine-today-list {
  display: grid;
  gap: 6px;
  padding: 8px 12px 10px;
}

.routine-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  padding: 6px 10px;
  border: 1px solid #efd7a4;
  border-left: 4px solid var(--routine, #c47b1a);
  border-radius: 12px;
  background: #fffaf0;
}

.routine-item.is-done {
  background: #fff;
}

.routine-item.is-done .routine-title {
  color: var(--muted);
  text-decoration: line-through;
}

.routine-check {
  width: 28px;
  height: 28px;
  border: 1.5px solid #c47b1a;
  border-radius: 50%;
  color: transparent;
  background: #fff;
  font-weight: 800;
}

.routine-item.is-done .routine-check {
  color: #fff;
  background: #c47b1a;
}

.routine-title {
  margin: 0;
  font-size: 14px;
}

.routine-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 1px;
  color: #8a5a12;
  font-size: 12px;
}

.routine-empty {
  padding: 8px 2px 2px;
  color: var(--muted);
  line-height: 1.7;
}

.routine-empty button {
  padding: 0;
  border: 0;
  color: var(--green);
  background: transparent;
  font-weight: 700;
}

.routine-feedback {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.routine-feedback button {
  min-height: 28px;
  padding: 0 10px;
  border: 0;
  border-radius: 999px;
  color: #8a5a12;
  background: #fff4d8;
  font-size: 12px;
  font-weight: 750;
}

.routine-feedback button.is-running {
  color: #fff;
  background: #c47b1a;
}
</style>
