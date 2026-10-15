<script setup lang="ts">
// 感悟卡片 —— 平移 web-legacy/app.js memoCardMarkup / memoReadMarkup / readStampCaption /
// readCountLabel / memoSourceMarkup(427) / noteHeadingMarkup(420) / playReadStamp(2463)
import { computed, nextTick, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { Memo } from '../../types/api'
import { useMemoStore } from '../../stores/memo'
import { useDayStore } from '../../stores/day'
import { useUiStore } from '../../stores/ui'
import { imageUrl } from '../../api/images'
import { formatMinutes } from '../../utils/format'
import { formatMemoDate } from '../../utils/date'
import { copyTextToClipboard, escapeHtml, renderMemoHtml, safeHttpUrl, splitTags } from '../../utils/note'
import ReadStamp from './ReadStamp.vue'

const props = defineProps<{ memo: Memo }>()

const emit = defineEmits<{
  (e: 'edit', memo: Memo): void
}>()

const memoStore = useMemoStore()
const dayStore = useDayStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()

const daily = computed(() => props.memo.kind === 'daily')
const tags = computed(() => splitTags(props.memo.tags))

// ---------- 来源头部（平移 memoSourceMarkup；有 routine/thread 来源时可点击过滤） ----------
const sourceTarget = computed<{ kind: 'routine' | 'thread'; id: number } | null>(() => {
  const memo = props.memo
  if (memo.source_routine_id) return { kind: 'routine', id: memo.source_routine_id }
  if (memo.source_thread_id) return { kind: 'thread', id: memo.source_thread_id }
  return null
})

const sourceMarkup = computed(() => {
  const memo = props.memo
  if (memo.source_kind === 'routine' && memo.source_title) {
    return `<div class="memo-source"><span>来自每日必做</span><strong>${escapeHtml(memo.source_title)}</strong></div>`
  }
  if (memo.source_thread_title || (memo.source_kind === 'thread' && memo.source_title)) {
    const threadTitle = memo.source_thread_title || memo.source_title
    const step =
      memo.source_entry_id && memo.source_title && memo.source_title !== threadTitle
        ? `<em>这一步：${escapeHtml(memo.source_title)}</em>`
        : ''
    return `<div class="memo-source"><span>来自主线</span><strong>${escapeHtml(threadTitle ?? '')}</strong>${step}</div>`
  }
  if (!memo.source_title) return ''
  const estimate = Number(memo.source_estimate_minutes || 0)
    ? `预估 ${formatMinutes(Number(memo.source_estimate_minutes))}`
    : '未设预估'
  const actual = `实际 ${formatMinutes(Number(memo.source_actual_seconds || 0) / 60)}`
  return `<div class="memo-source"><span>来自任务</span><strong>${escapeHtml(memo.source_title)}</strong><em>${escapeHtml(`${estimate} · ${actual}`)}</em></div>`
})

function openSource() {
  const target = sourceTarget.value
  if (!target) return
  memoStore.openMemoSource(target.kind, target.id)
  if (route.name !== 'memos') void router.push('/memos')
}

// ---------- note_title / note_link 头部（平移 noteHeadingMarkup + noteLinkMarkup） ----------
const noteLinkHref = computed(() => safeHttpUrl(props.memo.note_link ?? ''))
const noteTitle = computed(() => String(props.memo.note_title || '').trim())

// ---------- 点阅徽章（平移 memoReadMarkup / readCountLabel / readStampCaption） ----------
const readCount = computed(() => Number(props.memo.read_count) || 0)
const readToday = computed(() => Boolean(props.memo.read_today))

function formatReadMoment(value: string | null): string {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)
}

const readLabel = computed(() => {
  const times = readCount.value
  if (!times) return '看完点一下，今天记一次'
  if (readToday.value) return `今天已阅，累计 ${times} 遍。明天再点会再记一遍`
  const when = formatReadMoment(props.memo.last_read_at)
  return when
    ? `已阅 ${times} 遍，上次 ${when}。今天再点一次`
    : `已阅 ${times} 遍。今天再点一次`
})

const readTone = computed(() => (readToday.value ? 'is-today' : readCount.value ? 'has-count' : ''))

function readStampCaption(count: number): string {
  const marks: Record<number, string> = {
    1: '第一遍',
    2: '又看了一眼',
    3: '第三遍，有点熟了',
    5: '五遍，记在身上',
    7: '七遍了',
    10: '十遍印',
    21: '二十一遍，真记得',
    50: '五十遍',
    100: '百读不厌',
  }
  if (marks[count]) return marks[count]
  if (count > 0 && count % 10 === 0) return `${count} 遍整`
  return `第 ${count} 遍`
}

// ---------- 打卡印章动画（平移 playReadStamp 的 1400ms 状态） ----------
const stamping = ref(false)
const stampToken = ref(0)
const stampCount = ref(0)
const stampMilestone = ref(false)

const popBadge = ref(false)

async function onRead() {
  if (readToday.value) return
  const counted = await memoStore.markMemoRead(props.memo.kind, props.memo.id)
  if (!counted) return
  const count = Number(props.memo.read_count) || 0
  stampCount.value = count
  stampMilestone.value = count === 1 || count % 10 === 0 || [3, 5, 7, 21].includes(count)
  const token = ++stampToken.value
  stamping.value = true
  window.setTimeout(() => {
    if (stampToken.value === token) stamping.value = false
  }, 1400)
  popBadge.value = false
  await nextTick()
  popBadge.value = true
  window.setTimeout(() => {
    popBadge.value = false
  }, 450)
}

// ---------- 正文里的复制链接按钮（平移 copyLink，委托自 v-html 内容） ----------
function onContentClick(event: MouseEvent) {
  const button = (event.target as HTMLElement).closest('[data-action="copy-link"]')
  if (!button) return
  event.preventDefault()
  event.stopPropagation()
  const url = button.getAttribute('data-url') || ''
  void copyTextToClipboard(url).then((ok) => {
    if (button.textContent) button.textContent = '已复制'
    window.setTimeout(() => {
      if (button.textContent) button.textContent = '复制'
    }, 1200)
    if (ok) ui.notify('链接已复制')
  })
}

function viewImage(index: number) {
  ui.openImageViewer(props.memo.images, index)
}

// ---------- 头部动作 ----------
function onPromote() {
  void memoStore.promoteMemo(props.memo, dayStore.date)
}

function onOpenDay() {
  dayStore.setDate(props.memo.memo_date)
  void router.push('/today')
}

const contentHtml = computed(() => renderMemoHtml(props.memo.content))

// 空白点击点阅由 MemoFeed 委托到这里（平移 legacy 卡片空白 markMemoRead → playReadStamp）
defineExpose({ onRead })
</script>

<template>
  <article
    class="memo-card"
    :class="{
      'is-pinned': memo.pinned,
      'is-read-today': memo.read_today,
      'is-stamping': stamping,
    }"
  >
    <div class="memo-card-header">
      <span>{{ memo.pinned ? '📌 ' : '' }}{{ formatMemoDate(memo.memo_date) }}{{ daily ? ' · 每日感悟' : '' }}</span>
      <div class="memo-card-actions">
        <button
          type="button"
          class="memo-read-mark"
          :class="[readTone, { 'is-pop': popBadge }]"
          :title="readLabel"
          :aria-label="readLabel"
          @click.stop="onRead"
        >
          <span class="memo-read-seal" aria-hidden="true">{{ readToday ? '已阅' : '阅' }}</span>
          <strong v-if="readCount">{{ readCount }}</strong>
        </button>
        <button @click.stop="onPromote">加入今天</button>
        <button v-if="daily" @click.stop="onOpenDay">打开当天</button>
        <template v-else>
          <button @click.stop="memoStore.toggleMemoPin(memo)">{{ memo.pinned ? '取消置顶' : '置顶' }}</button>
          <button @click.stop="emit('edit', memo)">编辑</button>
        </template>
      </div>
    </div>
    <div
      v-if="sourceMarkup"
      class="memo-source-jump"
      :class="{ 'is-clickable': sourceTarget }"
      @click.stop="openSource"
      v-html="sourceMarkup"
    ></div>
    <div v-if="noteTitle || noteLinkHref" class="memo-note-heading">
      <strong v-if="noteTitle">{{ noteTitle }}</strong>
      <a
        v-if="noteLinkHref"
        class="memo-link"
        :href="noteLinkHref"
        target="_blank"
        rel="noopener noreferrer"
        @click.stop
      >{{ noteLinkHref }}</a>
    </div>
    <div v-if="memo.content" class="memo-content" v-html="contentHtml" @click="onContentClick"></div>
    <div v-if="memo.images && memo.images.length" class="image-strip">
      <span v-for="(image, index) in memo.images" :key="image.id" class="image-tile">
        <button
          type="button"
          class="image-thumb"
          aria-label="查看原图"
          @click.stop="viewImage(index)"
        >
          <img :src="imageUrl(image.id, true)" alt="图片缩略图" />
        </button>
      </span>
    </div>
    <div v-if="tags.length" class="memo-tags">
      <span v-for="tag in tags" :key="tag" class="memo-tag">#{{ tag }}</span>
    </div>
    <ReadStamp
      v-if="stamping"
      :count="stampCount"
      :caption="readStampCaption(stampCount)"
      :milestone="stampMilestone"
    />
  </article>
</template>

<style scoped>
.memo-card {
  position: relative;
  overflow: hidden;
  padding: 18px 19px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(28, 45, 37, 0.045);
  cursor: pointer;
}

.memo-card:hover {
  border-color: #c9d8cf;
}

.memo-card.is-pinned {
  border-color: #d4c9ed;
  box-shadow: inset 3px 0 #8e83bf;
}

.memo-card.is-pinned:hover {
  border-color: #d4c9ed;
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

.memo-card-actions button.memo-read-mark {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 27px;
  padding: 0 8px 0 6px;
  border: 1px dashed #d7c4bf;
  border-radius: 999px;
  color: #a6847c;
  background: transparent;
  font-size: 10px;
  font-weight: 750;
}

.memo-card-actions button.memo-read-mark.has-count {
  border-style: solid;
  border-color: #ddd6d2;
  color: #8a817c;
  background: #f7f5f4;
}

.memo-card-actions button.memo-read-mark.is-today {
  border-style: solid;
  border-color: rgba(194, 59, 50, 0.55);
  color: #c23b32;
  background: #fff1ee;
  box-shadow: 0 0 0 3px rgba(194, 59, 50, 0.08);
}

.memo-card-actions button.memo-read-mark.is-today .memo-read-seal {
  width: auto;
  min-width: 28px;
  padding: 0 4px;
  border-radius: 999px;
  background: rgba(194, 59, 50, 0.12);
  font-size: 10px;
  letter-spacing: 0.04em;
}

.memo-read-seal {
  display: grid;
  width: 16px;
  height: 16px;
  place-items: center;
  border: 1.5px solid currentColor;
  border-radius: 50%;
  font-size: 9px;
  line-height: 1;
  transform: rotate(-8deg);
}

.memo-card-actions button.memo-read-mark strong {
  min-width: 0.8em;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  font-weight: 800;
}

.memo-card-actions button.memo-read-mark.is-pop strong {
  animation: read-count-pop 420ms cubic-bezier(0.2, 1.4, 0.3, 1);
}

.memo-card.is-stamping {
  z-index: 2;
  animation: memo-ink-flash 700ms ease;
}

.memo-source-jump.is-clickable {
  cursor: pointer;
}

.memo-note-heading {
  display: grid;
  gap: 4px;
  margin-bottom: 8px;
}

.memo-note-heading strong {
  font-size: 15px;
}

.memo-link {
  color: var(--green);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.memo-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 13px;
}

.memo-tag {
  padding: 3px 7px;
  border-radius: 999px;
  color: var(--purple);
  background: #f1eef9;
  font-size: 10px;
}

.image-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.image-tile {
  position: relative;
  width: 72px;
  height: 72px;
}

.image-thumb {
  width: 72px;
  height: 72px;
  padding: 0;
  border: 1px solid rgba(23, 32, 29, 0.08);
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
  cursor: zoom-in;
}

.image-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.memo-content :deep(.note-link) {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 6px 0;
}

.memo-content :deep(.note-link a) {
  min-width: 0;
  color: var(--green-dark);
  font-weight: 650;
  overflow-wrap: anywhere;
}

.memo-content :deep(.note-link a:hover) {
  text-decoration: underline;
}

.memo-content :deep(.copy-link) {
  flex: 0 0 auto;
  min-height: 26px;
  padding: 0 8px;
  border: 1px solid var(--line);
  border-radius: 7px;
  color: var(--muted);
  background: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

@keyframes read-count-pop {
  0% {
    transform: scale(0.4);
  }

  60% {
    transform: scale(1.28);
  }

  100% {
    transform: scale(1);
  }
}

@keyframes memo-ink-flash {
  0%,
  100% {
    background: #fff;
  }

  35% {
    background: #fff8f6;
  }
}

@media (prefers-reduced-motion: reduce) {
  .memo-card-actions button.memo-read-mark.is-pop strong,
  .memo-card.is-stamping {
    animation: none;
  }
}
</style>
