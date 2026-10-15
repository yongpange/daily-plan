<script setup lang="ts">
// 任务面板 —— 平移 renderTasks / threadCardHtml / createTask / showAddTask / bindTaskMove。
// taskList = 主线卡片（threads）+ 非主线家族的散任务（TaskRow）；
// 右滑顺延（pointer 事件，横向 ≥64px）打开 MoveTaskPopover。
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useDayStore } from '../../stores/day'
import { useDialogStore } from '../../stores/dialogs'
import { useMemoStore } from '../../stores/memo'
import { useUiStore } from '../../stores/ui'
import router from '../../router'
import type { Entry, ThreadDay } from '../../types/api'
import { formatHours } from '../../utils/format'
import { formatMonthDay } from '../../utils/date'
import { entriesInTreeOrder, entriesUnderTask, outcomeText, threadTaskIds } from './taskUtils'
import TaskRow from './TaskRow.vue'
import EditTaskDialog from '../dialogs/EditTaskDialog.vue'
import FocusDialog from '../dialogs/FocusDialog.vue'
import MoveTaskPopover from '../dialogs/MoveTaskPopover.vue'

// types/api.ts 的 ThreadDay 未声明运行时契约里的扩展字段（契约禁改），本地扩展读取。
type ThreadDayExt = ThreadDay & {
  today_entry_id?: number | null
  needs_followup?: boolean
  note_count?: number
}

const dayStore = useDayStore()
const dialogsStore = useDialogStore()
const memoStore = useMemoStore()
const ui = useUiStore()

// ---------- 主线卡片（平移 threadCardHtml，类型 ThreadDayExt） ----------

const threads = computed(() => (dayStore.threads ?? []) as ThreadDayExt[])

function threadRootEntry(thread: ThreadDayExt): Entry | undefined {
  return dayStore.entries.find((entry) => entry.id === thread.today_entry_id)
}

function threadStepRows(thread: ThreadDayExt) {
  const root = threadRootEntry(thread)
  if (!root) return []
  const family = entriesUnderTask(root.task_id, dayStore.entries)
  return entriesInTreeOrder(family).map(({ entry, depth }) => ({ entry, depth }))
}

function threadRecentLabel(thread: ThreadDayExt): string {
  return dayStore.threadRecentText(thread)
}

function threadAction(thread: ThreadDayExt, action: 'feature' | 'pause' | 'resume' | 'done') {
  const payload =
    action === 'feature'
      ? { featured: true }
      : action === 'pause'
        ? { status: 'paused' as const }
        : action === 'resume'
          ? { status: 'active' as const }
          : { status: 'done' as const }
  void dayStore.updateThread(thread.id, payload).catch((error: unknown) => {
    ui.notify(error instanceof Error ? error.message : '保存失败', true)
  })
}

function openThreadNote(thread: ThreadDayExt) {
  dialogsStore.openTaskNote({ kind: 'thread', threadId: thread.id, title: thread.title })
}

function openAllThreadNotes(thread: ThreadDayExt) {
  memoStore.openMemoSource('thread', thread.id)
  void router.push({ name: 'memos' })
}

// 每条主线的“今天这一步”输入（平移 thread-step-form）
const threadStepDraft = reactive<Record<number, string>>({})
function submitThreadStep(thread: ThreadDayExt) {
  const step = (threadStepDraft[thread.id] || '').trim()
  if (!step) return
  void dayStore
    .submitThreadStep(thread.id, step)
    .then(() => {
      threadStepDraft[thread.id] = ''
    })
    .catch((error: unknown) => {
      ui.notify(error instanceof Error ? error.message : '保存失败', true)
    })
}

// ---------- 散任务（平移 renderTasks 的 loose 过滤） ----------

const rows = computed(() => {
  const list = dayStore.entries
  const family = threadTaskIds(list)
  const loose = list.filter(
    (entry) =>
      outcomeText(entry) !== 'carried' &&
      outcomeText(entry) !== 'rescheduled' &&
      (entry.task_id == null || !family.has(entry.task_id)),
  )
  return entriesInTreeOrder(loose).map(({ entry, depth }) => ({ entry, depth }))
})

const showEmpty = computed(() => rows.value.length === 0 && threads.value.length === 0)
const showList = computed(() => rows.value.length > 0 || threads.value.length > 0)

// 计划负荷提示（平移 renderSummary 末尾 capacity 逻辑：叶子任务 + 必做）
const capacityMinutes = computed(() => {
  const visible = dayStore.entries.filter(
    (entry) =>
      outcomeText(entry) !== 'carried' &&
      outcomeText(entry) !== 'rescheduled' &&
      !entry.has_children,
  )
  const planned = visible.reduce((sum, entry) => sum + (Number(entry.estimate_minutes) || 0), 0)
  const routinePlanned = dayStore.todayRoutines.reduce(
    (sum, routine) => sum + (Number(routine.estimate_minutes) || 0),
    0,
  )
  return planned + routinePlanned
})

const capacityHeavy = computed(() => capacityMinutes.value > 480)
const capacityHint = computed(() => {
  const planned = capacityMinutes.value
  if (planned > 480) return `计划 ${formatHours(planned)}，负荷偏高`
  return planned ? `计划负荷 ${formatHours(planned)}` : ''
})

const threadFormDisabled = computed(() => dayStore.activeThreads.length >= 2)
const threadFormDisabledTitle = computed(() =>
  threadFormDisabled.value ? '同时进行的主线最多两条。先把一条暂停或做完。' : '',
)

// ---------- 主线表单 ----------

const threadFormVisible = ref(false)
const threadTitle = ref('')
const threadDoneWhen = ref('')
const threadStep = ref('')
const threadProject = ref('')

function openThreadForm() {
  threadFormVisible.value = true
}

function cancelThread() {
  threadFormVisible.value = false
  threadTitle.value = ''
  threadDoneWhen.value = ''
  threadStep.value = ''
  threadProject.value = ''
}

async function submitThread() {
  try {
    await dayStore.submitThread({
      title: threadTitle.value,
      done_when: threadDoneWhen.value,
      step: threadStep.value,
      project_name: threadProject.value || undefined,
    })
    cancelThread()
    ui.notify('主线已经开始，今天这一步在清单最上面')
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '保存失败', true)
  }
}

// ---------- 添加任务表单（平移 showAddTask / createTask） ----------

const addFormVisible = ref(false)
const parentEntry = ref<Entry | null>(null)
const newTaskTitle = ref('')
const newTaskProject = ref('')
const newTaskEstimate = ref('60')
const newTaskStart = ref('')
const addBusy = ref(false)

function showAddTask(parent: Entry | null = null) {
  parentEntry.value = parent
  addFormVisible.value = true
  if (parent?.project_name) newTaskProject.value = parent.project_name
  window.setTimeout(() => newTaskTitleInput.value?.focus(), 0)
}

function hideAddTask() {
  parentEntry.value = null
  addFormVisible.value = false
  newTaskTitle.value = ''
  newTaskProject.value = ''
  newTaskEstimate.value = '60'
  newTaskStart.value = ''
}

const newTaskTitleInput = ref<HTMLInputElement | null>(null)

async function submitAddTask() {
  if (addBusy.value) return
  addBusy.value = true
  try {
    await dayStore.createTask({
      title: newTaskTitle.value,
      project_name: newTaskProject.value || undefined,
      estimate_minutes: Number(newTaskEstimate.value) || 0,
      planned_start: newTaskStart.value || undefined,
      parent_entry_id: parentEntry.value?.id,
    })
    hideAddTask()
    ui.notify('任务已加入今天')
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '添加失败', true)
  } finally {
    addBusy.value = false
  }
}

// ---------- 编辑 / 专注对话框 ----------

const editTarget = ref<Entry | null>(null)
const editOpen = ref(false)
function openEdit(entry: Entry) {
  editTarget.value = entry
  editOpen.value = true
}

const focusTarget = ref<Entry | null>(null)
const focusOpen = ref(false)
function openFocus(entry: Entry) {
  focusTarget.value = entry
  focusOpen.value = true
}

// ---------- 右滑顺延（平移 bindTaskMove） ----------

const moveEntry = ref<Entry | null>(null)
const moveRow = ref<HTMLElement | null>(null)
let drag: {
  pointerId: number
  row: HTMLElement
  entryId: number
  startX: number
  startY: number
  active: boolean
} | null = null
let ignoreNextClick = false

function resetDrag() {
  if (!drag) return
  drag.row.style.transform = ''
  drag.row.classList.remove('is-dragging', 'is-move-ready')
  drag = null
}

function onPointerDown(event: PointerEvent) {
  if (event.button !== 0) return
  const target = event.target as HTMLElement
  if (target.closest('button, a, input, textarea, .task-note')) return
  const row = target.closest('.task-row') as HTMLElement | null
  if (!row) return
  const entry = dayStore.entries.find((item) => item.id === Number(row.dataset.entryId))
  if (!entry || outcomeText(entry) !== 'planned') return
  drag = {
    pointerId: event.pointerId,
    row,
    entryId: entry.id,
    startX: event.clientX,
    startY: event.clientY,
    active: false,
  }
  row.setPointerCapture?.(event.pointerId)
}

function onPointerMove(event: PointerEvent) {
  if (!drag || event.pointerId !== drag.pointerId) return
  const dx = event.clientX - drag.startX
  const dy = event.clientY - drag.startY
  if (!drag.active) {
    if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return
    if (Math.abs(dy) > Math.abs(dx)) {
      resetDrag()
      return
    }
    drag.active = true
    drag.row.classList.add('is-dragging')
  }
  const shift = Math.max(0, Math.min(dx * 0.28, 28))
  drag.row.style.transform = shift ? `translateX(${shift}px)` : ''
  drag.row.classList.toggle('is-move-ready', dx >= 64)
}

function onPointerUp(event: PointerEvent) {
  if (!drag || event.pointerId !== drag.pointerId) return
  const dx = event.clientX - drag.startX
  const ready = drag.active && dx >= 64
  const row = drag.row
  const entryId = drag.entryId
  resetDrag()
  if (!ready) return
  ignoreNextClick = true
  const entry = dayStore.entries.find((item) => item.id === entryId)
  if (!entry) return
  moveEntry.value = entry
  moveRow.value = row
}

function onPointerCancel(event: PointerEvent) {
  if (!drag || event.pointerId !== drag.pointerId) return
  resetDrag()
}

function closeMovePopover() {
  moveEntry.value = null
  moveRow.value?.classList.remove('is-move-open')
  moveRow.value = null
}

async function moveTaskTo(targetDate: string) {
  const entry = moveEntry.value
  if (!entry || !targetDate) return
  try {
    const result = await dayStore.moveTaskTo(entry.id, targetDate)
    ui.notify(`「${entry.title || result.title}」已移到 ${formatMonthDay(result.moved_to)}`)
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '改期失败', true)
  } finally {
    closeMovePopover()
  }
}

// 弹窗外部点击关闭（平移 document click 监听；忽略滑块松开后的那一次 click）
function onDocumentClick(event: MouseEvent) {
  if (ignoreNextClick) {
    ignoreNextClick = false
    return
  }
  if (!moveEntry.value) return
  const target = event.target as HTMLElement
  if (target.closest('.move-popover') || target.closest('.task-row.is-move-open')) return
  closeMovePopover()
}

function onDocumentKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && moveEntry.value) closeMovePopover()
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onDocumentKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>

<template>
  <section class="panel task-panel">
    <div class="panel-header">
      <div>
        <h2>今天要做的事</h2>
      </div>
      <div class="task-heading-actions">
        <span id="capacityHint" class="capacity-hint" :class="{ 'is-heavy': capacityHeavy }">
          {{ capacityHint }}
        </span>
        <button
          id="openThreadForm"
          type="button"
          class="button subtle"
          :disabled="threadFormDisabled"
          :title="threadFormDisabledTitle"
          @click="openThreadForm"
        >
          开一条主线
        </button>
        <button
          v-if="!addFormVisible"
          id="toggleAddTask"
          class="button primary"
          @click="showAddTask()"
        >
          ＋ 添加任务
        </button>
      </div>
    </div>

    <form v-if="threadFormVisible" id="threadForm" class="thread-form" @submit.prevent="submitThread">
      <label>
        <span>主线</span>
        <input v-model="threadTitle" type="text" maxlength="80" placeholder="例如：选品结论" required />
      </label>
      <label>
        <span>做到怎样算完</span>
        <input
          v-model="threadDoneWhen"
          type="text"
          maxlength="200"
          placeholder="一句话，例如：能讲清这个细分做不做"
          required
        />
      </label>
      <label>
        <span>今天这一步</span>
        <input
          v-model="threadStep"
          type="text"
          maxlength="240"
          placeholder="今天具体推进的那一句"
          required
        />
      </label>
      <label>
        <span>项目（可选）</span>
        <input
          v-model="threadProject"
          type="text"
          maxlength="80"
          list="projectOptions"
          placeholder="用来分类，不是主线本身"
        />
      </label>
      <div class="form-actions">
        <button type="button" class="button subtle" @click="cancelThread">取消</button>
        <button type="submit" class="button primary">开始这条主线</button>
      </div>
    </form>

    <form v-if="addFormVisible" id="addTaskForm" class="add-task-form" @submit.prevent="submitAddTask">
      <div v-if="parentEntry" id="subtaskContext" class="subtask-context">
        正在为 <strong>{{ parentEntry.title }}</strong> 添加子任务
        <button type="button" @click="hideAddTask">取消</button>
      </div>
      <label class="wide-field">
        <span>任务名称</span>
        <input
          id="newTaskTitle"
          ref="newTaskTitleInput"
          v-model="newTaskTitle"
          name="title"
          type="text"
          maxlength="240"
          autocomplete="off"
          placeholder="写清楚下一步动作，例如：整理访谈提纲"
          required
        />
      </label>
      <label>
        <span>项目（可选）</span>
        <input
          id="newTaskProject"
          v-model="newTaskProject"
          name="project"
          type="text"
          maxlength="80"
          list="projectOptions"
          placeholder="例如：飞书抓取"
        />
      </label>
      <label>
        <span>预估分钟</span>
        <input
          id="newTaskEstimate"
          v-model="newTaskEstimate"
          name="estimate"
          type="number"
          min="0"
          max="1440"
          step="5"
          required
        />
      </label>
      <label>
        <span>计划开始（可选）</span>
        <input id="newTaskStart" v-model="newTaskStart" name="plannedStart" type="time" />
      </label>
      <div class="estimate-presets wide-field" aria-label="常用预估时间">
        <span>快捷：</span>
        <button type="button" @click="newTaskEstimate = '15'">15 分钟</button>
        <button type="button" @click="newTaskEstimate = '30'">30 分钟</button>
        <button type="button" @click="newTaskEstimate = '45'">45 分钟</button>
        <button type="button" @click="newTaskEstimate = '60'">1 小时</button>
        <button type="button" @click="newTaskEstimate = '90'">1.5 小时</button>
        <button type="button" @click="newTaskEstimate = '120'">2 小时</button>
      </div>
      <div class="form-actions wide-field">
        <button type="button" class="button subtle" @click="hideAddTask">取消</button>
        <button type="submit" class="button primary" :disabled="addBusy">
          {{ addBusy ? '添加中…' : '加入今天' }}
        </button>
      </div>
    </form>

    <datalist id="projectOptions">
      <option v-for="project in dayStore.day?.projects ?? []" :key="project.id" :value="project.name" />
    </datalist>

    <div
      v-if="showList"
      id="taskList"
      class="task-list"
      aria-live="polite"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerCancel"
    >
      <section
        v-for="thread in threads"
        :key="thread.id"
        class="thread-card"
        :class="{ 'is-featured': thread.featured, 'is-paused': thread.status === 'paused' }"
      >
        <div class="thread-head">
          <span class="thread-kicker">
            {{
              thread.status === 'paused'
                ? '暂停的主线'
                : thread.featured
                  ? '今天主推'
                  : '另一条主线'
            }}
          </span>
          <h3>
            <span v-if="thread.project_name" class="project-tag">{{ thread.project_name }}</span>
            {{ thread.title }}
          </h3>
          <span class="thread-done">做到：{{ thread.done_when }}</span>
        </div>
        <p class="thread-recent">{{ threadRecentLabel(thread) }}</p>
        <div class="thread-actions">
          <template v-if="thread.status === 'paused'">
            <button type="button" @click="openThreadNote(thread)">写感悟</button>
            <button type="button" @click="openAllThreadNotes(thread)">
              全部感悟{{ thread.note_count ? ` · ${thread.note_count}` : '' }}
            </button>
            <button type="button" @click="threadAction(thread, 'resume')">恢复</button>
          </template>
          <template v-else>
            <button v-if="!thread.featured" type="button" @click="threadAction(thread, 'feature')">
              今天主推
            </button>
            <button type="button" @click="openThreadNote(thread)">写感悟</button>
            <button type="button" @click="openAllThreadNotes(thread)">
              全部感悟{{ thread.note_count ? ` · ${thread.note_count}` : '' }}
            </button>
            <button type="button" @click="threadAction(thread, 'pause')">暂停</button>
            <button type="button" @click="threadAction(thread, 'done')">做完</button>
          </template>
        </div>
        <form
          v-if="thread.status !== 'paused' && (!threadRootEntry(thread) || threadRootEntry(thread)?.outcome === 'abandoned')"
          class="thread-step-form"
          @submit.prevent="submitThreadStep(thread)"
        >
          <input
            v-model="threadStepDraft[thread.id]"
            type="text"
            maxlength="240"
            required
            placeholder="今天这一步做什么"
            aria-label="今天这一步"
          />
          <button type="submit">写下今天这一步</button>
        </form>
        <div v-else-if="threadRootEntry(thread)" class="thread-step">
          <TaskRow
            v-for="row in threadStepRows(thread)"
            :key="row.entry.id"
            :entry="row.entry"
            :depth="row.depth"
            @edit="openEdit"
            @focus="openFocus"
            @subtask="showAddTask"
          />
        </div>
      </section>

      <TaskRow
        v-for="row in rows"
        :key="row.entry.id"
        :entry="row.entry"
        :depth="row.depth"
        @edit="openEdit"
        @focus="openFocus"
        @subtask="showAddTask"
      />
    </div>

    <div v-if="showEmpty" id="emptyTasks" class="empty-state">
      <div class="empty-icon">✓</div>
      <h3>今天还没有安排</h3>
      <p>先写下一件真正值得推进的事，再估一个大致时间。</p>
      <button class="button primary" data-action="show-add" @click="showAddTask()">
        添加第一条任务
      </button>
    </div>

    <EditTaskDialog :open="editOpen" :entry="editTarget" @close="editOpen = false" />
    <FocusDialog :open="focusOpen" :entry="focusTarget" @close="focusOpen = false" />
    <MoveTaskPopover
      v-if="moveEntry"
      :entry="moveEntry"
      :anchor="moveRow"
      @close="closeMovePopover"
      @move="moveTaskTo"
    />
  </section>
</template>

<style scoped>
.task-heading-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.capacity-hint {
  color: var(--muted);
  font-size: 11px;
}

.capacity-hint.is-heavy {
  color: var(--red);
  font-weight: 700;
}

.task-list {
  padding: 7px 0;
}

.empty-state {
  padding: 58px 24px 62px;
  text-align: center;
}

.empty-state .empty-icon {
  display: grid;
  width: 52px;
  height: 52px;
  margin: 0 auto 14px;
  place-items: center;
  border-radius: 16px;
  color: var(--green);
  background: var(--green-soft);
  font-size: 22px;
}

.empty-state h3 {
  margin-bottom: 7px;
}

.empty-state p {
  margin-bottom: 18px;
  color: var(--muted);
}

.add-task-form {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 120px 132px;
  gap: 12px;
  padding: 18px 22px;
  border-bottom: 1px solid var(--line);
  background: #fafcfb;
}

.add-task-form label {
  display: grid;
  align-content: start;
  gap: 6px;
}

.add-task-form label > span {
  color: #59645f;
  font-size: 11px;
  font-weight: 750;
}

.wide-field,
.subtask-context,
.estimate-presets,
.add-task-form .form-actions {
  grid-column: 1 / -1;
}

.subtask-context {
  padding: 9px 11px;
  border-radius: 8px;
  color: #466054;
  background: var(--green-soft);
  font-size: 12px;
}

.subtask-context button {
  float: right;
  border: 0;
  color: var(--green);
  background: transparent;
  font-weight: 700;
}

.estimate-presets {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
  color: var(--muted);
  font-size: 11px;
}

.estimate-presets button {
  min-height: 28px;
  padding: 0 9px;
  border: 1px solid var(--line);
  border-radius: 7px;
  color: #53605a;
  background: #fff;
  font-size: 11px;
}

.estimate-presets button:hover {
  border-color: #8fb5a2;
  color: var(--green);
}

.form-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.thread-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 12px;
  margin: 0 18px 8px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fbfcfb;
}

.thread-form label {
  display: grid;
  align-content: start;
  gap: 6px;
}

.thread-form label > span {
  color: #59645f;
  font-size: 11px;
  font-weight: 750;
}

.thread-form label:nth-child(3),
.thread-form .form-actions {
  grid-column: 1 / -1;
}

.thread-card {
  margin: 8px 14px 4px;
  padding: 12px 12px 2px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fbfcfb;
}

.thread-card.is-featured {
  background: #fbfcfb;
}

.thread-card.is-paused {
  background: #f7f8f7;
}

.thread-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.thread-kicker {
  flex: 0 0 auto;
  margin: 0;
  color: #8a7342;
  font-size: 11px;
  font-weight: 750;
}

.thread-card h3 {
  margin: 0;
  font-size: 16px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thread-done {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thread-recent {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}

.thread-actions,
.thread-step-form {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-top: 8px;
}

.thread-actions button,
.thread-step-form button {
  min-height: 28px;
  padding: 0 10px;
  border: 0;
  border-radius: 999px;
  color: var(--green);
  background: var(--soft);
  font-size: 12px;
  font-weight: 700;
}

.thread-step-form {
  margin-bottom: 8px;
}

.thread-step-form input {
  flex: 1;
  min-width: 180px;
  height: 36px;
}

.thread-card :deep(.task-row) {
  margin-right: -12px;
  margin-left: -12px;
  padding-right: 12px;
  padding-left: 12px;
}
</style>
