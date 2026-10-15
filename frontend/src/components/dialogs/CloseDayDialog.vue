<script setup lang="ts">
// 收工复盘对话框 —— 平移 openCloseDay / renderCloseTasks / updateCloseTaskDetails /
// submitCloseDay（app.js 1930-2220）。decisions 联动逻辑与校验逐项保留。
// closeMood 是本地状态（确认收工时才随表单提交）。
import { computed, reactive, ref, watch } from 'vue'
import BaseDialog from '../common/BaseDialog.vue'
import { closeDay } from '../../api/day'
import { useDayStore } from '../../stores/day'
import { useUiStore } from '../../stores/ui'
import type { CloseDecision, Entry, ThreadDay } from '../../types/api'
import { shiftDate } from '../../utils/date'
import { outcomeText } from '../today/taskUtils'

const props = defineProps<{ open: boolean }>()

const emit = defineEmits<{ (e: 'close'): void }>()

const dayStore = useDayStore()
const ui = useUiStore()

// types/api.ts 的 ThreadDay 未声明契约里的 needs_followup/today_entry_id（契约禁改），本地扩展。
type ThreadDayExt = ThreadDay & {
  today_entry_id?: number | null
  needs_followup?: boolean
}

interface DecisionDraft {
  action: string
  reason: string
  targetDate: string
  nextEstimate: string
  note: string
  nextStep: string
}

const reflection = ref('')
const closeMood = ref<number | null>(null)
const busy = ref(false)
const drafts = reactive<Record<number, DecisionDraft>>({})
const formRef = ref<HTMLFormElement | null>(null)

const threads = computed(() => (dayStore.threads ?? []) as ThreadDayExt[])

/** 平移 renderCloseTasks：未完成的叶子任务 */
const pendingEntries = computed(() =>
  dayStore.entries.filter((entry) => outcomeText(entry) === 'planned' && !entry.has_children),
)

/** 平移 renderCloseTasks：主线今天这一步已完成、需要写下一句的条目 */
const followupEntries = computed(() =>
  dayStore.entries.filter((entry) =>
    threads.value.some(
      (thread) => thread.needs_followup && thread.today_entry_id === entry.id,
    ),
  ),
)

const tomorrow = computed(() => shiftDate(dayStore.date, 1))

const reasonOptions = computed(() => dayStore.day?.reasons ?? [])

function emptyDraft(entry: Entry): DecisionDraft {
  return {
    action: '',
    reason: '',
    targetDate: tomorrow.value,
    nextEstimate: String(Number(entry.estimate_minutes) || 0),
    note: '',
    nextStep: '',
  }
}

function draftOf(entry: Entry): DecisionDraft {
  if (!drafts[entry.id]) drafts[entry.id] = emptyDraft(entry)
  return drafts[entry.id]
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    reflection.value = dayStore.day?.day.reflection || ''
    closeMood.value = dayStore.mood
    Object.keys(drafts).forEach((key) => delete drafts[Number(key)])
    pendingEntries.value.forEach((entry) => {
      drafts[entry.id] = emptyDraft(entry)
    })
  },
)

// ---------- 平移 updateCloseTaskDetails 的联动 ----------

function showDetails(draft: DecisionDraft): boolean {
  return Boolean(draft.action) && draft.action !== 'completed'
}

function showTarget(draft: DecisionDraft): boolean {
  return draft.action === 'reschedule'
}

function showEstimate(draft: DecisionDraft): boolean {
  return ['carry', 'reschedule'].includes(draft.action)
}

function showNextStep(entry: Entry, draft: DecisionDraft): boolean {
  if (!entry.thread_id) return false
  return ['completed', 'carry', 'reschedule'].includes(draft.action)
}

function nextStepLabel(draft: DecisionDraft): string {
  return draft.action === 'carry' ? '卡在哪，明天从这里开始' : '明天接着做的一句'
}

function pickCloseMood(value: number) {
  closeMood.value = value
}

// ---------- 平移 submitCloseDay ----------

function focusField(entryId: number, field: string) {
  const form = formRef.value
  const card = form?.querySelector(`[data-close-entry="${entryId}"]`)
  const input = card?.querySelector(`[data-field="${field}"]`) as HTMLElement | null
  input?.focus()
}

async function submit() {
  const decisions: CloseDecision[] = []
  for (const entry of followupEntries.value) {
    const draft = draftOf(entry)
    const nextStep = draft.nextStep.trim()
    if (!nextStep) {
      ui.notify('这条主线要写下明天的下一句', true)
      focusField(entry.id, 'next-step')
      return
    }
    decisions.push({ entry_id: entry.id, action: 'completed', next_step: nextStep })
  }
  for (const entry of pendingEntries.value) {
    const draft = draftOf(entry)
    if (!draft.action) {
      ui.notify('请为每一条任务选择去向', true)
      focusField(entry.id, 'action')
      return
    }
    const incomplete = draft.action !== 'completed'
    const reason = draft.reason || undefined
    if (incomplete && !reason) {
      ui.notify('未完成的任务需要选择主要原因', true)
      focusField(entry.id, 'reason')
      return
    }
    const targetDate =
      draft.action === 'carry' ? tomorrow.value : draft.action === 'reschedule' ? draft.targetDate : undefined
    const nextStep = draft.nextStep.trim()
    if (entry.thread_id && draft.action !== 'abandoned' && !nextStep) {
      ui.notify(
        draft.action === 'carry' ? '写下卡在哪里，明天从这里开始' : '这条主线要写下明天的下一句',
        true,
      )
      focusField(entry.id, 'next-step')
      return
    }
    decisions.push({
      entry_id: entry.id,
      action: draft.action as CloseDecision['action'],
      reason,
      note: draft.note || undefined,
      target_date: targetDate,
      next_estimate_minutes: Number(draft.nextEstimate) || 0,
      next_step: nextStep,
    })
  }

  if (busy.value) return
  busy.value = true
  try {
    await closeDay({
      date: dayStore.date,
      focus: dayStore.focusDraft,
      reflection: reflection.value,
      mood: closeMood.value,
      decisions,
    })
    emit('close')
    await dayStore.loadDay()
    ui.notify('今天已经收好，记录会进入复盘报告')
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '收工失败', true)
  } finally {
    busy.value = false
  }
}

/** cancel 提交器直接关闭（method=dialog 的平移） */
function onSubmit(event: SubmitEvent) {
  const submitter = event.submitter as HTMLButtonElement | null
  if (submitter?.value === 'cancel') {
    emit('close')
    return
  }
  event.preventDefault()
  void submit()
}
</script>

<template>
  <BaseDialog :open="open" @close="emit('close')">
    <form ref="formRef" class="close-day-dialog" method="dialog" @submit="onSubmit">
      <div class="dialog-header">
        <div>
          <p class="eyebrow">把今天关好</p>
          <h2>收工复盘</h2>
          <p>未完成不是红色警告，而是给未来计划留下证据。</p>
        </div>
        <button class="dialog-close" value="cancel" aria-label="关闭">×</button>
      </div>

      <div id="closeDayTasks" class="close-day-tasks">
        <div v-if="!pendingEntries.length && !followupEntries.length" class="empty-inline">
          今天的任务已经全部处理，可以直接写下感悟并收工。
        </div>

        <article
          v-for="entry in followupEntries"
          :key="entry.id"
          class="close-task"
          :data-close-entry="entry.id"
          data-followup="1"
        >
          <strong>{{ entry.title }}</strong>
          <p class="thread-recent">这一步已经完成。写下明天接着做的一句，主线才会接上。</p>
          <label class="note-field">
            <span>明天接着做的一句</span>
            <input
              v-model="draftOf(entry).nextStep"
              data-field="next-step"
              type="text"
              maxlength="240"
              placeholder="明天打开就能接着做的那一句"
            />
          </label>
        </article>

        <article
          v-for="entry in pendingEntries"
          :key="entry.id"
          class="close-task"
          :data-close-entry="entry.id"
        >
          <strong>{{ entry.title }}</strong>
          <div class="close-task-grid">
            <label>
              <span>这条任务怎么处理</span>
              <select v-model="draftOf(entry).action" data-field="action" required>
                <option value="">请选择去向</option>
                <option value="completed">其实已经完成</option>
                <option value="carry">明天继续</option>
                <option value="reschedule">改到其他日期</option>
                <option value="abandoned">放弃，不再做</option>
              </select>
            </label>
            <div v-if="showDetails(draftOf(entry))" class="close-task-details" data-details>
              <label>
                <span>没完成的主要原因</span>
                <select v-model="draftOf(entry).reason" data-field="reason">
                  <option value="">请选择原因</option>
                  <option v-for="reason in reasonOptions" :key="reason.value" :value="reason.value">
                    {{ reason.label }}
                  </option>
                </select>
              </label>
              <label v-if="showTarget(draftOf(entry))" data-target-wrap>
                <span>改到哪一天</span>
                <input
                  v-model="draftOf(entry).targetDate"
                  data-field="target-date"
                  type="date"
                  :min="tomorrow"
                />
              </label>
              <label v-if="showEstimate(draftOf(entry))" data-estimate-wrap>
                <span>下次预估分钟</span>
                <input
                  v-model="draftOf(entry).nextEstimate"
                  data-field="next-estimate"
                  type="number"
                  min="0"
                  max="1440"
                  step="5"
                />
              </label>
              <label class="note-field">
                <span>补充一句（可选）</span>
                <input
                  v-model="draftOf(entry).note"
                  data-field="note"
                  type="text"
                  maxlength="1000"
                  placeholder="下次怎么避免，或卡在哪里？"
                />
              </label>
            </div>
            <label
              v-if="showNextStep(entry, draftOf(entry))"
              class="note-field"
              data-next-wrap
            >
              <span>{{ nextStepLabel(draftOf(entry)) }}</span>
              <input
                v-model="draftOf(entry).nextStep"
                data-field="next-step"
                type="text"
                maxlength="240"
                placeholder="明天打开就能接着做的那一句"
              />
            </label>
          </div>
        </article>
      </div>

      <label>
        <span>今天的感悟</span>
        <textarea
          id="closeReflection"
          v-model="reflection"
          rows="4"
          maxlength="8000"
          placeholder="今天学到了什么？"
        ></textarea>
      </label>

      <fieldset class="mood-picker dialog-mood">
        <legend>今天的状态</legend>
        <div>
          <button
            v-for="value in [1, 2, 3, 4, 5]"
            :key="value"
            type="button"
            :data-close-mood="value"
            :class="{ 'is-active': closeMood === value }"
            @click="pickCloseMood(value)"
          >
            {{ value }}
          </button>
        </div>
      </fieldset>

      <div class="dialog-actions">
        <button class="button subtle" value="cancel">稍后再说</button>
        <button type="submit" class="button dark" :disabled="busy">
          {{ busy ? '正在收工…' : '确认收工' }}
        </button>
      </div>
    </form>
  </BaseDialog>
</template>

<style scoped>
label {
  display: grid;
  align-content: start;
  gap: 6px;
}

label > span {
  color: #59645f;
  font-size: 11px;
  font-weight: 750;
}

.dialog-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.empty-inline {
  padding: 26px 8px;
  color: var(--muted);
  text-align: center;
  font-size: 12px;
}

.close-day-dialog {
  width: min(780px, calc(100% - 30px));
}

.close-day-tasks {
  display: grid;
  gap: 10px;
  margin-bottom: 20px;
}

.close-task {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fafcfb;
}

.close-task > strong {
  display: block;
  margin-bottom: 10px;
}

.close-task .thread-recent {
  margin: -4px 0 10px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}

.close-task-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
}

.close-task-grid > label {
  margin: 0 !important;
}

.close-task-details {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-column: 1 / -1;
  gap: 9px;
}

.close-task-details .note-field {
  grid-column: 1 / -1;
}

.dialog-mood {
  margin: 17px 0 0;
}

.mood-picker {
  margin: 0;
  padding: 0;
  border: 0;
}

.mood-picker legend {
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 650;
}

.mood-picker > div {
  display: flex;
  gap: 6px;
}

.mood-picker button {
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: #4e5a55;
  background: #fff;
  font-size: 12px;
  font-weight: 700;
}

.mood-picker button.is-active {
  border-color: #8fb5a2;
  color: var(--green-dark);
  background: var(--green-soft);
}
</style>
