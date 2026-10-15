<script setup lang="ts">
// 任务/必做/主线感悟对话框 —— 平移 web-legacy/index.html L948-998（taskNoteDialog）+
// app.js showNoteDialog(3882) / loadTaskNoteHistory(3902) / submitTaskNote(3974)
// 全局挂载在 App.vue，由 dialogsStore.taskNoteTarget/taskNoteOpen 控制
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { Memo } from '../../types/api'
import { createMemo, fetchMemos } from '../../api/memos'
import { uploadImage } from '../../api/images'
import { useDayStore } from '../../stores/day'
import { useMemoStore } from '../../stores/memo'
import type { PendingImage } from '../../stores/memo'
import { useDialogStore } from '../../stores/dialogs'
import { useUiStore } from '../../stores/ui'
import { renderMemoHtml, safeHttpUrl } from '../../utils/note'
import { prepareImage } from '../../utils/image'
import { formatMemoDate } from '../../utils/date'
import { formatMinutes } from '../../utils/format'
import BaseDialog from '../common/BaseDialog.vue'
import RichNoteEditor from '../common/RichNoteEditor.vue'
import ImageComposer from '../common/ImageComposer.vue'
import TagPresets from '../common/TagPresets.vue'
import MemoImageStrip from '../common/MemoImageStrip.vue'

const route = useRoute()
const dayStore = useDayStore()
const memoStore = useMemoStore()
const dialogsStore = useDialogStore()
const ui = useUiStore()

const richRef = ref<{
  insertTemplateContent: (content: string) => void
  writeRich: (content: string) => void
  readRich: () => string
} | null>(null)

const content = ref('')
const noteTitle = ref('')
const noteLink = ref('')
const noteTags = ref('')
const history = ref<Memo[]>([])
const pendingImages = ref<PendingImage[]>([])
const draftMemoId = ref<number | null>(null)
const submitting = ref(false)

function templateTarget() {
  return richRef.value
    ? { insertTemplateContent: (c: string) => richRef.value?.insertTemplateContent(c) }
    : null
}

// ---------- meta / hint / placeholder（平移 openTaskNote/openRoutineFeedback/openThreadFeedback 的入参） ----------
const target = computed(() => dialogsStore.taskNoteTarget)

const targetEntry = computed(() =>
  target.value?.entryId != null
    ? dayStore.entries.find((entry) => entry.id === target.value?.entryId) ?? null
    : null,
)

const targetThread = computed(() => {
  const threadId = targetEntry.value?.thread_id ?? null
  if (threadId == null) return null
  return dayStore.threads.find((thread) => thread.id === threadId) ?? null
})

const taskNoteMeta = computed(() => {
  const current = target.value
  if (!current) return ''
  const dateLabel = formatMemoDate(dayStore.date)
  if (current.kind === 'routine') return `${dateLabel} · 每日必做`
  if (current.kind === 'thread') {
    const thread = dayStore.threads.find((item) => item.id === current.threadId)
    return thread
      ? `${dateLabel} · 主线 · 做到：${thread.done_when}`
      : `${dateLabel} · 主线`
  }
  const entry = targetEntry.value
  if (!entry) return dateLabel
  const estimate = entry.estimate_minutes
    ? `预估 ${formatMinutes(entry.estimate_minutes)}`
    : '未设预估'
  const actual = `实际 ${formatMinutes(entry.actual_seconds / 60)}`
  const thread = targetThread.value
  return `${dateLabel} · ${estimate} · ${actual}${thread ? ` · 主线 ${thread.title}` : ''}`
})

const taskNoteHint = computed(() => {
  const current = target.value
  if (!current) return ''
  if (current.kind === 'routine') return '保存后出现在感悟库，并能按这项必做一次看完。'
  if (current.kind === 'thread') return '保存后归到这条主线下面，感悟库里可以一次看完。'
  if (current.kind === 'task') return ''
  return '保存后会出现在右侧随手记录和感悟库里，并带上这条任务的标题、预估和实际时间。'
})

const editorPlaceholder = computed(() => {
  const current = target.value
  if (current?.kind === 'routine') return '今天看完，留下什么？'
  if (current?.kind === 'thread') return '这条主线今天推进之后，留下什么？'
  return '做到这里，想留下什么？'
})

const historyHeading = computed(() => '当天已经写在这条主任务下的感悟')

// ---------- 打开：重置表单 + task 类加载历史（平移 showNoteDialog/loadTaskNoteHistory） ----------
watch(
  () => dialogsStore.taskNoteTarget,
  async (current) => {
    if (!current) return
    content.value = ''
    noteTitle.value = ''
    noteLink.value = ''
    noteTags.value = ''
    history.value = []
    pendingImages.value = []
    draftMemoId.value = null
    await nextTick()
    richRef.value?.writeRich('')
    if (current.kind === 'task') {
      void loadTaskNoteHistory(current)
    }
  },
)

function resolveTaskId(current: NonNullable<typeof target.value>): number | null {
  if (current.taskId != null) return current.taskId
  if (current.entryId == null) return null
  const entry = dayStore.entries.find((item) => item.id === current.entryId)
  return entry?.task_id ?? null
}

async function loadTaskNoteHistory(current: NonNullable<typeof target.value>) {
  const requestedTaskId = resolveTaskId(current)
  const requestedDate = current.date || targetEntry.value?.plan_date || dayStore.date
  if (requestedTaskId == null) return
  try {
    const notes = await fetchMemos({
      task_id: requestedTaskId,
      date: requestedDate,
      limit: 100,
    })
    const openTarget = dialogsStore.taskNoteTarget
    const openedDate = openTarget?.date || targetEntry.value?.plan_date || dayStore.date
    const stillSame =
      dialogsStore.taskNoteOpen &&
      openTarget?.kind === 'task' &&
      openTarget.entryId === current.entryId &&
      openedDate === requestedDate
    if (!stillSame) return
    const items = (notes || []).filter(
      (item) =>
        item.kind === 'memo' &&
        item.memo_date === requestedDate &&
        Number(item.source_task_id) === Number(requestedTaskId),
    )
    history.value = [...items].reverse()
  } catch {
    history.value = []
  }
}

function historyLinkHref(link: string | null): string {
  return safeHttpUrl(link ?? '')
}

async function addFiles(files: File[]) {
  for (const file of files) {
    if (pendingImages.value.length >= 9) {
      ui.notify('一条记录最多 9 张图片', true)
      break
    }
    try {
      const prepared = await prepareImage(file)
      pendingImages.value.push({
        localId: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        preview: prepared.thumbnail,
        prepared,
      })
    } catch (error) {
      ui.notify(error instanceof Error ? error.message : '图片处理失败', true)
    }
  }
}

function removePending(localId: string) {
  pendingImages.value = pendingImages.value.filter((item) => item.localId !== localId)
}

async function uploadPending(ownerKey: number) {
  const queue = [...pendingImages.value]
  pendingImages.value = []
  for (let index = 0; index < queue.length; index += 1) {
    try {
      await uploadImage({
        owner_type: 'memo',
        owner_key: String(ownerKey),
        ...queue[index].prepared,
      })
    } catch (error) {
      pendingImages.value = queue.slice(index)
      throw error
    }
  }
}

// ---------- 提交（平移 submitTaskNote） ----------
async function onSubmit() {
  const current = target.value
  if (!current || submitting.value) return
  const text = richRef.value?.readRich() ?? content.value
  if (!text && !pendingImages.value.length && !draftMemoId.value) {
    ui.notify('先写下一点感悟，或添加一张图片', true)
    return
  }
  submitting.value = true
  try {
    let memoId = draftMemoId.value
    if (!memoId) {
      const memo = await createMemo({
        date: current.date || dayStore.date,
        content: text,
        content_format: 'rich',
        tags: noteTags.value,
        note_title: noteTitle.value,
        note_link: noteLink.value,
        has_images: pendingImages.value.length > 0,
        ...(current.entryId != null ? { entry_id: current.entryId } : {}),
        ...(current.kind === 'routine' && current.routineId != null
          ? { routine_id: current.routineId }
          : {}),
        ...(current.kind === 'thread' && current.threadId != null
          ? { thread_id: current.threadId }
          : {}),
      })
      memoId = Number(memo.id)
      draftMemoId.value = memoId
    }
    try {
      await uploadPending(memoId)
    } catch {
      ui.notify('文字已经保存，剩下的图片可以再点一次保存', true)
      return
    }
    draftMemoId.value = null
    pendingImages.value = []
    dialogsStore.closeTaskNote()
    content.value = ''
    richRef.value?.writeRich('')
    if (route.name === 'today') await dayStore.loadDay()
    if (route.name === 'memos') await memoStore.loadMemos()
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '保存失败', true)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <BaseDialog :open="dialogsStore.taskNoteOpen" @close="dialogsStore.closeTaskNote">
    <form id="taskNoteForm" @submit.prevent="onSubmit">
      <div class="dialog-header">
        <div>
          <p class="eyebrow">记一句</p>
          <h2 id="taskNoteTitle">{{ target?.title }}</h2>
          <p id="taskNoteMeta">{{ taskNoteMeta }}</p>
        </div>
        <button
          id="closeTaskNote"
          class="dialog-close"
          type="button"
          aria-label="关闭"
          @click="dialogsStore.closeTaskNote"
        >
          ×
        </button>
      </div>
      <div v-if="history.length" id="taskNoteHistory" class="task-note-history">
        <p>{{ historyHeading }}</p>
        <article v-for="note in history" :key="String(note.id)">
          <header>
            <strong>{{ note.note_title || '未写标题' }}</strong>
            <time>{{ formatMemoDate(note.memo_date) }}</time>
          </header>
          <a
            v-if="historyLinkHref(note.note_link)"
            class="memo-link"
            :href="historyLinkHref(note.note_link)"
            target="_blank"
            rel="noopener noreferrer"
          >{{ historyLinkHref(note.note_link) }}</a>
          <div v-if="note.content" class="memo-content" v-html="renderMemoHtml(note.content)"></div>
          <MemoImageStrip :images="note.images" />
        </article>
      </div>
      <div class="field-row task-note-fields">
        <label>
          <span>标题</span>
          <input
            id="taskNoteHeading"
            v-model="noteTitle"
            type="text"
            maxlength="80"
            placeholder="给这则感悟起个名字，可留空"
          />
        </label>
        <label>
          <span>链接</span>
          <input
            id="taskNoteLink"
            v-model="noteLink"
            type="url"
            maxlength="500"
            placeholder="https:// 打开后在新标签页查看"
          />
        </label>
      </div>
      <RichNoteEditor
        ref="richRef"
        v-model="content"
        with-template
        :placeholder="editorPlaceholder"
        @paste-image="addFiles"
        @template="dialogsStore.openTemplate(templateTarget())"
      />
      <ImageComposer
        :pending="pendingImages"
        @add-files="addFiles"
        @remove-pending="removePending"
      />
      <label>
        <span>标签</span>
        <input
          id="taskNoteTags"
          v-model="noteTags"
          type="text"
          maxlength="300"
          placeholder="用逗号分隔，可留空"
        />
        <TagPresets v-model="noteTags" tag-input-id="taskNoteTags" />
      </label>
      <p v-if="taskNoteHint" id="taskNoteHint" class="task-note-hint">{{ taskNoteHint }}</p>
      <div class="dialog-actions">
        <button id="cancelTaskNote" class="button subtle" type="button" @click="dialogsStore.closeTaskNote">
          取消
        </button>
        <button type="submit" class="button primary" :disabled="submitting">
          {{ submitting ? '保存中…' : '保存到感悟库' }}
        </button>
      </div>
    </form>
  </BaseDialog>
</template>

<style scoped>
/* 标题和链接并排。全局 field-row 是三列窄格，链接会被挤到 115px，而且相邻 label 会多出上边距。 */
:global(dialog.dialog:has(#taskNoteForm)) {
  width: min(760px, calc(100% - 30px));
}

.task-note-fields {
  grid-template-columns: 220px minmax(0, 1fr);
  align-items: end;
}

.task-note-fields label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  margin-top: 0;
}

.task-note-fields input {
  width: 100%;
}

/* 平移 web-legacy/styles.css L2415-2451（task-note-history） */
.task-note-history {
  display: grid;
  gap: 8px;
  max-height: 240px;
  margin-bottom: 12px;
  overflow: auto;
  padding-right: 4px;
}

.task-note-history > p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}

.task-note-history article {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #f6f8f7;
}

.task-note-history header {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--muted);
  font-size: 12px;
}

.task-note-history header strong {
  color: var(--ink);
}

.memo-link {
  color: var(--green);
  font-size: 12px;
  overflow-wrap: anywhere;
}

/* 历史正文来自 v-html，富文本排版由 base.css 提供 */
.memo-content {
  font-size: 14px;
  line-height: 1.7;
}
</style>
