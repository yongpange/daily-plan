<script setup lang="ts">
// 随手记面板 —— 平移 quickMemoForm / submitQuickMemo / renderTodayMemos / 今日 mood 选择。
// 提交走 memoStore.submitMemo（POST + 图片上传 + 失败 PATCH 重试都在 store 里）。
import { onMounted, ref } from 'vue'
import { useDayStore } from '../../stores/day'
import { useMemoStore } from '../../stores/memo'
import { useDialogStore } from '../../stores/dialogs'
import { useUiStore } from '../../stores/ui'
import type { Memo } from '../../types/api'
import { formatMinutes } from '../../utils/format'
import { renderMemoHtml } from '../../utils/note'
import { imageUrl } from '../../api/images'
import RichNoteEditor from '../common/RichNoteEditor.vue'
import ImageComposer from '../common/ImageComposer.vue'
import TagPresets from '../common/TagPresets.vue'
import MoodPicker from '../common/MoodPicker.vue'

const dayStore = useDayStore()
const memoStore = useMemoStore()
const dialogsStore = useDialogStore()
const ui = useUiStore()

const content = ref('')
const tags = ref('')
const busy = ref(false)
const editorRef = ref<{ insertTemplateContent: (value: string) => void; writeRich: (value: string) => void } | null>(null)

onMounted(() => {
  void memoStore.loadSuggestedTags().catch(() => {})
})

async function submit() {
  if (busy.value) return
  busy.value = true
  try {
    const ok = await memoStore.submitMemo({
      bucket: 'quick',
      date: dayStore.date,
      content: content.value,
      tags: tags.value,
    })
    if (ok) {
      content.value = ''
      tags.value = ''
      // 清空编辑器（平移 clearRich）
      editorRef.value?.writeRich('')
    }
  } finally {
    busy.value = false
  }
}

function onTemplate() {
  dialogsStore.openTemplate(editorRef.value)
}

function addFiles(files: File[]) {
  void memoStore.addFilesToBucket(files, 'quick')
}

/** 平移 memoSourceMarkup */
function sourceHtml(memo: Memo): string {
  if (memo.source_kind === 'routine' && memo.source_title) {
    return `<div class="memo-source"><span>来自每日必做</span><strong>${escapeSource(
      memo.source_title,
    )}</strong></div>`
  }
  if (memo.source_thread_title || (memo.source_kind === 'thread' && memo.source_title)) {
    const threadTitle = memo.source_thread_title || memo.source_title || ''
    const step =
      memo.source_entry_id && memo.source_title && memo.source_title !== threadTitle
        ? `<em>这一步：${escapeSource(memo.source_title)}</em>`
        : ''
    return `<div class="memo-source"><span>来自主线</span><strong>${escapeSource(
      threadTitle,
    )}</strong>${step}</div>`
  }
  if (!memo.source_title) return ''
  const estimate = Number(memo.source_estimate_minutes || 0)
    ? `预估 ${formatMinutes(Number(memo.source_estimate_minutes) || 0)}`
    : '未设预估'
  const actual = `实际 ${formatMinutes(Number(memo.source_actual_seconds || 0) / 60)}`
  return `<div class="memo-source"><span>来自任务</span><strong>${escapeSource(
    memo.source_title,
  )}</strong><em>${estimate} · ${actual}</em></div>`
}

// 来源字段来自后端（memoSourceMarkup 原本就 escapeHtml），这里兜底一次。
function escapeSource(value: string): string {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function memoHtml(memo: Memo): string {
  return renderMemoHtml(memo.content)
}

function viewImage(memo: Memo, index: number) {
  ui.openImageViewer(memo.images, index)
}
</script>

<template>
  <section class="panel quick-memo-panel">
    <div class="panel-header compact-header">
      <div>
        <p class="eyebrow">随手记录</p>
        <h2>记一条</h2>
      </div>
    </div>
    <form id="quickMemoForm" class="quick-memo-form" @submit.prevent="submit">
      <RichNoteEditor
        ref="editorRef"
        v-model="content"
        with-template
        placeholder="刚刚想到什么？每条只记一个念头。也可以直接粘贴或拖入图片。"
        @paste-image="addFiles"
        @template="onTemplate"
      />
      <ImageComposer
        :pending="memoStore.pendingQuickImages"
        @add-files="addFiles"
        @remove-pending="(localId) => memoStore.removePendingImage('quick', localId)"
      />
      <input
        id="quickMemoTags"
        v-model="tags"
        type="text"
        maxlength="300"
        placeholder="标签，例如：估时, 产品"
      />
      <TagPresets v-model="tags" tag-input-id="quickMemoTags" />
      <button type="submit" class="button primary" :disabled="busy">
        {{ busy ? '保存中…' : '记下来' }}
      </button>
    </form>
    <div id="todayMemoList" class="today-memo-list">
      <div v-for="memo in memoStore.todayMemos" :key="memo.id" class="today-memo-item">
        <div v-if="sourceHtml(memo)" v-html="sourceHtml(memo)"></div>
        <div v-if="memo.content" class="memo-content" v-html="memoHtml(memo)"></div>
        <div v-if="memo.images?.length" class="image-strip">
          <span v-for="(image, index) in memo.images" :key="image.id" class="image-tile">
            <button type="button" class="image-thumb" aria-label="查看原图" @click="viewImage(memo, index)">
              <img :src="imageUrl(image.id, true)" alt="图片缩略图" />
            </button>
          </span>
        </div>
      </div>
    </div>
    <MoodPicker class="quick-mood" :model-value="dayStore.mood" @select="dayStore.setMood" />
  </section>
</template>

<style scoped>
.quick-memo-form {
  display: grid;
  gap: 9px;
  padding: 0 20px 17px;
}

.quick-memo-form textarea,
.quick-memo-form input {
  background: #fafcfb;
}

.quick-memo-form > button {
  justify-self: end;
}

.today-memo-list {
  display: grid;
  gap: 7px;
  padding: 0 20px 4px;
}

.today-memo-list:empty {
  display: none;
}

.today-memo-item {
  padding: 10px 11px;
  border-left: 3px solid #d9cfef;
  border-radius: 0 8px 8px 0;
  background: #f7f5fb;
  color: #4d4b59;
  font-size: 13px;
  line-height: 1.55;
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

.quick-mood {
  margin: 16px 20px 20px;
}
</style>
