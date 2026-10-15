<script setup lang="ts">
// 任务行（递归子任务）—— 平移 taskRowHtml。
// 秒级实际时间走 dayStore.aggregateSeconds（依赖 timerStore.now 每秒刷新）。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useDayStore } from '../../stores/day'
import { useTimerStore } from '../../stores/timer'
import { useDialogStore } from '../../stores/dialogs'
import { useMemoStore } from '../../stores/memo'
import { useUiStore } from '../../stores/ui'
import { errorMessage } from '../../api/http'
import { formatMinutes } from '../../utils/format'
import { localDateString } from '../../utils/date'
import { renderNote, copyTextToClipboard } from '../../utils/note'
import type { Entry } from '../../types/api'
import { isCompleted, isFinished, isPlanned, outcomeLabels, outcomeText } from './taskUtils'

const props = defineProps<{
  entry: Entry
  depth: number
}>()

const emit = defineEmits<{
  (e: 'edit', entry: Entry): void
  (e: 'focus', entry: Entry): void
  (e: 'subtask', entry: Entry): void
}>()

const dayStore = useDayStore()
const timerStore = useTimerStore()
const dialogsStore = useDialogStore()
const memoStore = useMemoStore()
const ui = useUiStore()

const completed = computed(() => isCompleted(props.entry))
const finished = computed(() => isFinished(props.entry))
const planned = computed(() => isPlanned(props.entry))
const isFutureDay = computed(() => dayStore.date > localDateString(new Date()))
const canComplete = computed(() => planned.value && !isFutureDay.value)

const menuOpen = ref(false)
const menuRoot = ref<HTMLElement | null>(null)

const actualSeconds = computed(() => dayStore.aggregateSeconds(props.entry))
const overEstimate = computed(
  () => props.entry.estimate_minutes > 0 && actualSeconds.value / 60 > props.entry.estimate_minutes,
)

const statusBadge = computed(() => {
  const outcome = outcomeText(props.entry)
  return !completed.value && outcomeLabels[outcome] ? outcomeLabels[outcome] : ''
})

const noteCount = computed(
  () =>
    memoStore.todayMemos.filter((memo) => {
      if (memo.kind !== 'memo') return false
      if (
        props.entry.task_id != null &&
        memo.source_task_id != null &&
        Number(memo.source_task_id) === Number(props.entry.task_id)
      ) {
        return true
      }
      return Number(memo.source_entry_id) === Number(props.entry.id)
    }).length,
)

const definitionHtml = computed(() => renderNote(props.entry.definition ?? ''))

const checkTitle = computed(() => {
  if (completed.value) return '已完成。要取消完成，点右侧 ···'
  if (isFutureDay.value) return '明天及以后的任务还不能标为完成'
  if (finished.value) return '这条任务已经结束'
  return '标为完成'
})

function toggleComplete() {
  if (completed.value) {
    ui.notify('要取消完成，请点任务右侧的 ···')
    return
  }
  if (isFutureDay.value) {
    ui.notify('明天及以后的任务还不能标为完成', true)
    return
  }
  if (!canComplete.value) return
  void dayStore.toggleComplete(props.entry).catch((error) => {
    ui.notify(errorMessage(error, '没能标为完成'), true)
  })
}

function toggleMenu() {
  menuOpen.value = !menuOpen.value
}

function closeMenu() {
  menuOpen.value = false
}

function editTask() {
  closeMenu()
  emit('edit', props.entry)
}

async function reopenTask() {
  closeMenu()
  try {
    await dayStore.reopenTask(props.entry)
    ui.notify('已取消完成')
  } catch (error) {
    ui.notify(errorMessage(error, '没能取消完成'), true)
  }
}

function onDocumentPointerDown(event: PointerEvent) {
  if (!menuOpen.value) return
  const root = menuRoot.value
  if (root && event.target instanceof Node && root.contains(event.target)) return
  closeMenu()
}

function onDocumentKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') closeMenu()
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('keydown', onDocumentKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('keydown', onDocumentKeydown)
})

function startTimer() {
  void timerStore.startTimer({ entryId: props.entry.id })
}

function stopTimer() {
  void timerStore.stopTimer({ entryId: props.entry.id })
}

function openNote() {
  dialogsStore.openTaskNote({
    kind: 'task',
    entryId: props.entry.id,
    taskId: props.entry.task_id ?? undefined,
    title: props.entry.title,
    date: dayStore.date,
  })
}

/** renderNote 生成的复制链接按钮（data-action="copy-link"） */
function onNoteClick(event: MouseEvent) {
  const button = (event.target as HTMLElement).closest('.copy-link') as HTMLElement | null
  if (!button) return
  const url = button.dataset.url || ''
  void copyTextToClipboard(url).then((ok) => {
    if (ok) ui.notify('链接已复制')
  })
}
</script>

<template>
  <article
    class="task-row"
    :class="{ 'is-completed': completed, 'is-finished': finished, 'is-menu-open': menuOpen }"
    :data-entry-id="entry.id"
    :data-depth="depth"
    :style="{ '--depth': depth }"
  >
    <button
      type="button"
      class="task-check"
      :class="{ 'is-locked': isFutureDay && !completed }"
      :disabled="finished && !completed"
      :aria-disabled="!canComplete || undefined"
      :title="checkTitle"
      :aria-label="checkTitle"
      @click="toggleComplete"
    >
      ✓
    </button>
    <div class="task-main">
      <div class="task-title-line">
        <span v-if="entry.project_name" class="project-tag">{{ entry.project_name }}</span>
        <h3 class="task-title">{{ entry.title }}</h3>
        <span v-if="statusBadge" class="outcome-badge">{{ statusBadge }}</span>
      </div>
      <div class="task-meta">
        <span v-if="entry.planned_start">{{ entry.planned_start }} 开始</span>
        <span v-if="entry.has_children"><span>含子任务</span></span>
        <span v-else>预估 <strong>{{ formatMinutes(entry.estimate_minutes) }}</strong></span>
        <span :class="{ 'over-estimate': overEstimate }">
          实际
          <strong class="actual-time" :data-entry-id="entry.id">
            {{ formatMinutes(actualSeconds / 60) }}
          </strong>
        </span>
        <span v-if="planned && !entry.thread_id" class="move-hint">右滑改期</span>
        <span v-if="entry.definition?.trim()" class="note-hint">有说明</span>
      </div>
      <div v-if="entry.definition?.trim()" class="task-note">
        <div class="task-note-card">
          <p>完成标准 / 补充说明</p>
          <div class="task-note-body" v-html="definitionHtml" @click="onNoteClick"></div>
        </div>
      </div>
    </div>
    <div class="task-actions">
      <button
        v-if="!finished && entry.is_running"
        class="task-action timer is-running"
        @click="stopTimer"
      >
        ■ 结束计时
      </button>
      <template v-else-if="!finished">
        <button class="task-action timer" @click="startTimer">▶ 开始</button>
        <button class="task-action focus" @click="emit('focus', entry)">◎ 专注</button>
      </template>
      <button v-if="!finished" class="task-action" @click="emit('subtask', entry)">＋ 子任务</button>
      <button
        v-if="!entry.parent_id"
        class="task-action note"
        @click="openNote"
      >
        写感悟{{ noteCount ? ` · ${noteCount}` : '' }}
      </button>
      <div ref="menuRoot" class="task-more-wrap">
        <button
          type="button"
          class="task-action task-more"
          aria-label="任务设置"
          aria-haspopup="menu"
          :aria-expanded="menuOpen"
          @click.stop="toggleMenu"
        >
          ···
        </button>
        <div v-if="menuOpen" class="task-menu" role="menu">
          <button type="button" role="menuitem" @click="editTask">编辑任务</button>
          <button v-if="completed" type="button" role="menuitem" @click="reopenTask">取消完成</button>
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped>
.task-row {
  --depth: 0;
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-height: 46px;
  margin-left: calc(var(--depth) * 27px);
  padding: 5px 12px 5px 14px;
  border-bottom: 1px solid #edf0ee;
  transition: background-color 120ms ease;
}

.task-row:last-child {
  border-bottom: 0;
}

.task-row:hover,
.task-row:focus-within,
.task-row.is-menu-open {
  z-index: 6;
  background: #fafcfb;
}

.note-hint {
  color: var(--green);
  font-weight: 750;
}

.task-note {
  display: none;
  position: absolute;
  z-index: 8;
  top: 100%;
  left: 36px;
  width: min(480px, calc(100% - 52px));
  padding-top: 8px;
}

.task-row:hover .task-note,
.task-row:focus-within .task-note {
  display: block;
}

.task-note-card {
  padding: 12px 14px;
  border: 1px solid #d7e2dc;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 16px 36px rgba(28, 45, 37, 0.14);
}

.task-note-card p {
  margin: 0 0 6px;
  color: var(--muted);
  font-size: 11px;
  font-weight: 750;
}

.task-note-body {
  color: var(--ink);
  font-size: 13px;
  line-height: 1.65;
  white-space: normal;
  overflow-wrap: anywhere;
  user-select: text;
}

.note-link {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 6px 0;
}

.note-link a {
  min-width: 0;
  color: var(--green-dark);
  font-weight: 650;
  overflow-wrap: anywhere;
}

.note-link a:hover {
  text-decoration: underline;
}

.copy-link {
  flex: 0 0 auto;
  min-height: 26px;
  padding: 0 8px;
  border: 1px solid var(--line);
  border-radius: 7px;
  color: #4e5a55;
  background: #fff;
  font-size: 11px;
  font-weight: 750;
}

.task-row[data-depth='1'],
.task-row[data-depth='2'],
.task-row[data-depth='3'] {
  position: relative;
}

.task-row[data-depth='1']::before,
.task-row[data-depth='2']::before,
.task-row[data-depth='3']::before {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 8px;
  width: 1px;
  background: #dce4df;
  content: '';
}

.task-check {
  position: relative;
  display: grid;
  width: 22px;
  height: 22px;
  flex: 0 0 auto;
  place-items: center;
  border: 1.5px solid #b7c2bc;
  border-radius: 8px;
  color: transparent;
  background: #fff;
  font-size: 14px;
  font-weight: 900;
}

.task-check:hover {
  border-color: var(--green);
}

.task-check.is-locked {
  cursor: not-allowed;
  opacity: 0.45;
}

.task-row.is-completed .task-check:disabled {
  cursor: default;
  opacity: 1;
}

.task-row.is-completed .task-check {
  border-color: var(--green);
  color: #fff;
  background: var(--green);
}

.task-row.is-completed .task-title {
  color: #89928e;
  text-decoration: line-through;
}

.task-row.is-finished:not(.is-completed) {
  opacity: 0.69;
}

.task-main {
  min-width: 0;
}

.task-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.task-title {
  overflow: hidden;
  margin: 0;
  font-size: 14px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-tag {
  flex: 0 0 auto;
  max-width: 115px;
  overflow: hidden;
  padding: 3px 7px;
  border-radius: 999px;
  color: var(--green);
  background: var(--green-soft);
  font-size: 10px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 1px;
  color: var(--muted);
  font-size: 11px;
}

.task-meta strong {
  color: #44504a;
  font-variant-numeric: tabular-nums;
}

.task-meta .over-estimate strong {
  color: var(--red);
}

.outcome-badge {
  padding: 2px 6px;
  border-radius: 5px;
  color: #795f27;
  background: var(--yellow-soft);
}

.task-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 5px;
}

.task-action {
  min-height: 28px;
  padding: 0 9px;
  border: 1px solid var(--line);
  border-radius: 8px;
  color: #5d6963;
  background: #fff;
  font-size: 11px;
  font-weight: 700;
}

.task-action:hover {
  border-color: #b6c7be;
  color: var(--green);
}

.move-hint {
  color: #9aa69f;
  font-size: 11px;
  opacity: 0;
  transition: opacity 120ms ease;
}

.task-row:hover .move-hint,
.task-row:focus-within .move-hint {
  opacity: 1;
}

.task-row.is-dragging {
  z-index: 3;
  background: #f3faf6;
  user-select: none;
}

.task-row.is-move-ready {
  background: #e7f6ee;
}

.task-action.note {
  border-color: #ddd4f3;
  color: #5c4d86;
  background: #f7f5fb;
}

.task-action.note:hover {
  border-color: #c8b7ea;
  color: #43356d;
}

.task-action.timer {
  min-width: 76px;
  border-color: #b9d5c7;
  color: var(--green-dark);
  background: var(--green-soft);
}

.task-action.timer.is-running {
  border-color: #e5aaaa;
  color: var(--red);
  background: var(--red-soft);
}

.task-action.focus {
  border-color: #dfd6f3;
  color: var(--purple);
  background: #f3f0fb;
}

.task-more-wrap {
  position: relative;
}

.task-more {
  width: 32px;
  padding: 0;
  font-size: 17px;
}

.task-menu {
  position: absolute;
  z-index: 12;
  top: calc(100% + 4px);
  right: 0;
  min-width: 132px;
  padding: 6px;
  border: 1px solid #d7e2dc;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 16px 36px rgba(28, 45, 37, 0.14);
}

.task-menu button {
  display: block;
  width: 100%;
  min-height: 32px;
  padding: 0 10px;
  border: 0;
  border-radius: 7px;
  color: #33403b;
  background: transparent;
  font-size: 12px;
  font-weight: 700;
  text-align: left;
}

.task-menu button:hover {
  color: var(--green);
  background: var(--green-soft);
}
</style>
