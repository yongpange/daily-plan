<script setup lang="ts">
// 感悟流 —— 平移 web-legacy/app.js renderMemos(2625) / taskMemoGroupMarkup(2580) /
// taskMemoPieceMarkup(2612) / isGroupedTaskMemo(2535) + memoFeed 点击委托(4613-4656)
import { computed, ref } from 'vue'
import type { Memo } from '../../types/api'
import { useMemoStore } from '../../stores/memo'
import { useDialogStore } from '../../stores/dialogs'
import { renderMemoHtml, safeHttpUrl } from '../../utils/note'
import { formatMemoDate } from '../../utils/date'
import MemoCard from './MemoCard.vue'
import MemoImageStrip from '../common/MemoImageStrip.vue'
import type MemoCardComponent from './MemoCard.vue'

const props = defineProps<{ query?: string }>()

const emit = defineEmits<{
  (e: 'edit', memo: Memo): void
}>()

const memoStore = useMemoStore()
const dialogsStore = useDialogStore()

const query = computed(() => (props.query ?? '').trim())

// ---------- 来源过滤摘要（平移 renderMemos 的 summary 文案） ----------
const sourceLabel = computed(() => {
  const source = memoStore.memoSource
  if (!source) return ''
  const sourceTitle = memoStore.memoSources.find(
    (item) => item.kind === source.kind && Number(item.id) === Number(source.id),
  )?.title
  if (!sourceTitle) return ''
  return source.kind === 'thread' ? `主线「${sourceTitle}」` : `「${sourceTitle}」`
})

const filterSummary = computed(() => {
  const total = memoStore.memos.length
  const label = sourceLabel.value
  if (label) {
    return query.value
      ? `${label}里，“${query.value}”找到 ${total} 条感悟`
      : `${label}的感悟 · ${total} 条`
  }
  return query.value
    ? `“${query.value}”找到 ${total} 条记录（包含每日感悟）`
    : `共显示 ${total} 条记录 · 看完点一下，一天记一遍`
})

const emptyText = computed(() =>
  sourceLabel.value
    ? `${sourceLabel.value}还没有写下感悟。记一句，就会收在这里。`
    : '还没有记录。想到一句就先记一句，不必等完整文章。',
)

// ---------- 同主任务感悟分组 ----------
// 一级任务上写的感悟都带 source_task_id。主线的今天这一步也会带主线来源，仍归到这条主任务。
function isParentTaskMemo(memo: Memo): boolean {
  return memo.kind === 'memo' && memo.source_task_id != null && memo.source_kind !== 'routine'
}

interface MemoGroup {
  key: string
  notes: Memo[]
}

const feedItems = computed<(Memo | MemoGroup)[]>(() => {
  const seenTasks = new Set<string>()
  const items: (Memo | MemoGroup)[] = []
  for (const memo of memoStore.memos) {
    if (!isParentTaskMemo(memo)) {
      items.push(memo)
      continue
    }
    const key = String(memo.source_task_id)
    if (seenTasks.has(key)) continue
    seenTasks.add(key)
    const notes = memoStore.memos.filter(
      (item) => isParentTaskMemo(item) && String(item.source_task_id) === key,
    )
    items.push({ key, notes })
  }
  return items
})

function orderedGroupNotes(group: MemoGroup): Memo[] {
  return [...group.notes].sort((left, right) => {
    const byDate = String(left.memo_date).localeCompare(String(right.memo_date))
    if (byDate) return byDate
    return Number(left.id) - Number(right.id)
  })
}

function groupLinkHref(link: string | null): string {
  return safeHttpUrl(link ?? '')
}

// ---------- 点击空白处点阅（平移 memoFeed 委托：排除控件与文本选区） ----------
// 印章动画在 MemoCard 内部完成，这里通过暴露的 onRead 触发（含 read_today/防重判断）
const cardRefs = ref(new Map<string, InstanceType<typeof MemoCardComponent>>())

function setCardRef(memo: Memo, el: unknown) {
  const key = `${memo.kind}:${memo.id}`
  if (el) cardRefs.value.set(key, el as InstanceType<typeof MemoCardComponent>)
  else cardRefs.value.delete(key)
}

function onCardBlankClick(event: MouseEvent, memo: Memo) {
  if (
    (event.target as HTMLElement).closest(
      'a, button, input, textarea, label, .image-thumb, .image-remove',
    )
  ) {
    return
  }
  const selection = window.getSelection()
  if (selection && !selection.isCollapsed) return
  cardRefs.value.get(`${memo.kind}:${memo.id}`)?.onRead()
}

// ---------- 分组卡片：继续写 ----------
function continueTask(group: MemoGroup) {
  const newest = orderedGroupNotes(group)[orderedGroupNotes(group).length - 1]
  dialogsStore.openTaskNote({
    kind: 'task',
    entryId: newest.source_entry_id ?? undefined,
    taskId: newest.source_task_id ?? undefined,
    title: newest.source_title || '这条任务',
    date: newest.memo_date || newest.source_plan_date || undefined,
  })
}
</script>

<template>
  <div>
    <p class="memo-filter-summary">{{ filterSummary }}</p>
    <div class="memo-feed">
      <div v-if="!memoStore.memos.length" class="panel empty-inline">{{ emptyText }}</div>
      <template
        v-for="item in feedItems"
        :key="'key' in item ? `group-${item.key}` : `${item.kind}-${item.id}`"
      >
        <MemoCard
          v-if="'memo_date' in item"
          :ref="(el) => setCardRef(item, el)"
          :memo="item"
          @click="onCardBlankClick($event, item)"
          @edit="emit('edit', $event)"
        />
        <article
          v-else
          class="memo-card memo-group"
          :class="{ 'is-pinned': item.notes.some((note) => note.pinned) }"
        >
          <div class="memo-card-header">
            <span>主任务 · {{ orderedGroupNotes(item).length }} 则感悟</span>
            <div class="memo-card-actions">
              <button type="button" @click="continueTask(item)">继续写</button>
            </div>
          </div>
          <div class="memo-source">
            <span>来自任务</span>
            <strong>{{ orderedGroupNotes(item)[orderedGroupNotes(item).length - 1].source_title || '未命名任务' }}</strong>
          </div>
          <details v-if="orderedGroupNotes(item).length > 1" class="memo-group-earlier">
            <summary>展开之前的 {{ orderedGroupNotes(item).length - 1 }} 则</summary>
            <section
              v-for="note in orderedGroupNotes(item).slice(0, -1)"
              :key="String(note.id)"
              class="memo-group-piece"
            >
              <header>
                <strong>{{ note.note_title || '未写标题' }}</strong>
                <time>{{ formatMemoDate(note.memo_date) }}</time>
              </header>
              <a
                v-if="groupLinkHref(note.note_link)"
                class="memo-link"
                :href="groupLinkHref(note.note_link)"
                target="_blank"
                rel="noopener noreferrer"
              >{{ groupLinkHref(note.note_link) }}</a>
              <div v-if="note.content" class="memo-content" v-html="renderMemoHtml(note.content)"></div>
              <MemoImageStrip :images="note.images" />
            </section>
          </details>
          <section class="memo-group-piece">
            <header>
              <strong>
                {{ orderedGroupNotes(item)[orderedGroupNotes(item).length - 1].note_title || '未写标题' }}
              </strong>
              <time>{{ formatMemoDate(orderedGroupNotes(item)[orderedGroupNotes(item).length - 1].memo_date) }}</time>
            </header>
            <a
              v-if="groupLinkHref(orderedGroupNotes(item)[orderedGroupNotes(item).length - 1].note_link)"
              class="memo-link"
              :href="groupLinkHref(orderedGroupNotes(item)[orderedGroupNotes(item).length - 1].note_link)"
              target="_blank"
              rel="noopener noreferrer"
            >{{ groupLinkHref(orderedGroupNotes(item)[orderedGroupNotes(item).length - 1].note_link) }}</a>
            <div
              v-if="orderedGroupNotes(item)[orderedGroupNotes(item).length - 1].content"
              class="memo-content"
              v-html="renderMemoHtml(orderedGroupNotes(item)[orderedGroupNotes(item).length - 1].content)"
            ></div>
            <MemoImageStrip :images="orderedGroupNotes(item)[orderedGroupNotes(item).length - 1].images" />
          </section>
        </article>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* memo-card 基础样式与 MemoCard 内保持一致（分组卡片直接在 feed 里渲染） */
.memo-card {
  position: relative;
  overflow: hidden;
  padding: 18px 19px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(28, 45, 37, 0.045);
}

.memo-card:hover {
  border-color: #c9d8cf;
}

.memo-card.is-pinned {
  border-color: #d4c9ed;
  box-shadow: inset 3px 0 #8e83bf;
}

.memo-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 11px;
  color: var(--muted);
  font-size: 10px;
}

.memo-card-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 5px;
}

.memo-card-actions button {
  min-height: 27px;
  padding: 0 8px;
  border: 0;
  border-radius: 7px;
  color: var(--muted);
  background: var(--soft);
  font-size: 10px;
}

.memo-filter-summary {
  min-height: 25px;
  margin: 0 0 8px;
  color: var(--muted);
  font-size: 11px;
}

.memo-feed {
  display: grid;
  gap: 11px;
}

.memo-group-earlier {
  margin: 8px 0;
}

.memo-group-earlier summary {
  margin-bottom: 8px;
  color: var(--green);
  font-size: 12px;
  font-weight: 750;
  cursor: pointer;
}

.memo-group-piece {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #f6f8f7;
}

.memo-group-piece + .memo-group-piece {
  margin-top: 8px;
}

.memo-group-piece header {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--muted);
  font-size: 12px;
}

.memo-group-piece header strong {
  color: var(--ink);
}

.memo-link {
  color: var(--green);
  font-size: 12px;
  overflow-wrap: anywhere;
}
</style>
