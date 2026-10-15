<script setup lang="ts">
// 编辑感悟对话框 —— 平移 web-legacy/index.html L882-946（memoDialog）+
// app.js openMemoEdit(2667) / saveMemoEdit(2680) / deleteMemo(2766)
// 挂载在 MemosView（editingMemo 由视图持有，全局仅一处使用）
import { nextTick, ref, watch } from 'vue'
import type { Memo, MemoImage } from '../../types/api'
import { useMemoStore } from '../../stores/memo'
import { useDialogStore } from '../../stores/dialogs'
import { useUiStore } from '../../stores/ui'
import { uploadImage } from '../../api/images'
import { prepareImage } from '../../utils/image'
import BaseDialog from '../common/BaseDialog.vue'
import RichNoteEditor from '../common/RichNoteEditor.vue'
import ImageComposer from '../common/ImageComposer.vue'
import TagPresets from '../common/TagPresets.vue'

const props = defineProps<{ memo: Memo | null }>()

const emit = defineEmits<{ (e: 'close'): void }>()

const memoStore = useMemoStore()
const dialogsStore = useDialogStore()
const ui = useUiStore()

const richRef = ref<{
  insertTemplateContent: (content: string) => void
  writeRich: (content: string) => void
  readRich: () => string
} | null>(null)

const content = ref('')
const memoEditDate = ref('')
const memoEditTags = ref('')
const memoEditPinned = ref(false)
const editingImages = ref<MemoImage[]>([])
const saving = ref(false)

function templateTarget() {
  return richRef.value
    ? { insertTemplateContent: (c: string) => richRef.value?.insertTemplateContent(c) }
    : null
}

// 打开时回填（平移 openMemoEdit）；新加图片直接上传并 push 到 editingImages
watch(
  () => props.memo,
  async (memo) => {
    if (!memo) return
    content.value = memo.content
    memoEditDate.value = memo.memo_date
    memoEditTags.value = memo.tags || ''
    memoEditPinned.value = Boolean(memo.pinned)
    editingImages.value = [...(memo.images || [])]
    await nextTick()
    richRef.value?.writeRich(memo.content)
  },
  { immediate: true },
)

async function onAddFiles(files: File[]) {
  const memo = props.memo
  if (!memo) return
  for (const file of files) {
    if (editingImages.value.length >= 9) {
      ui.notify('一条记录最多 9 张图片', true)
      break
    }
    try {
      const prepared = await prepareImage(file)
      const meta = await uploadImage({
        owner_type: 'memo',
        owner_key: String(memo.id),
        ...prepared,
      })
      editingImages.value.push({ id: meta.id, width: meta.width, height: meta.height })
    } catch (error) {
      ui.notify(error instanceof Error ? error.message : '图片上传失败', true)
    }
  }
}

async function onRemoveSaved(imageId: number) {
  try {
    await memoStore.deleteSavedImage(imageId)
    editingImages.value = editingImages.value.filter((image) => image.id !== imageId)
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '图片删除失败', true)
  }
}

async function onSave() {
  const memo = props.memo
  if (!memo || saving.value) return
  saving.value = true
  try {
    await memoStore.saveMemoEdit(Number(memo.id), {
      date: memoEditDate.value,
      content: richRef.value?.readRich() ?? content.value,
      tags: memoEditTags.value,
      pinned: memoEditPinned.value,
    })
    emit('close')
    await memoStore.loadMemos()
    ui.notify('感悟已更新')
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '保存失败', true)
  } finally {
    saving.value = false
  }
}

async function onDelete() {
  const memo = props.memo
  if (!memo) return
  if (!window.confirm('确定删除这条感悟吗？')) return
  try {
    await memoStore.deleteMemo(Number(memo.id))
    emit('close')
    ui.notify('感悟已删除')
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '删除失败', true)
  }
}
</script>

<template>
  <BaseDialog :open="memo !== null" @close="emit('close')">
    <form id="memoEditForm" method="dialog" @submit.prevent="onSave">
      <div class="dialog-header">
        <div>
          <p class="eyebrow">整理碎片感悟</p>
          <h2>编辑记录</h2>
        </div>
        <button type="button" class="dialog-close" value="cancel" aria-label="关闭" @click="emit('close')">×</button>
      </div>
      <label>
        <span>内容</span>
        <RichNoteEditor
          ref="richRef"
          v-model="content"
          with-template
          placeholder="也可以直接粘贴或拖入图片。"
          @template="dialogsStore.openTemplate(templateTarget())"
          @paste-image="onAddFiles"
        />
      </label>
      <ImageComposer
        :images="editingImages"
        removable
        @add-files="onAddFiles"
        @remove-saved="onRemoveSaved"
      />
      <div class="field-row memo-fields">
        <label>
          <span>日期</span>
          <input id="memoEditDate" v-model="memoEditDate" type="date" required />
        </label>
        <label>
          <span>标签</span>
          <input id="memoEditTags" v-model="memoEditTags" type="text" maxlength="300" />
          <TagPresets v-model="memoEditTags" tag-input-id="memoEditTags" />
        </label>
      </div>
      <label class="pin-option">
        <input id="memoEditPinned" v-model="memoEditPinned" type="checkbox" />
        <span>置顶这条记录</span>
      </label>
      <div class="dialog-actions split-actions">
        <button id="deleteMemo" type="button" class="button danger-text" @click="onDelete">
          删除
        </button>
        <div>
          <button type="button" class="button subtle" value="cancel" @click="emit('close')">取消</button>
          <button id="saveMemoEdit" type="submit" class="button primary" :disabled="saving">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </form>
  </BaseDialog>
</template>

<style scoped>
/* 平移 web-legacy/styles.css L2266-2268（memo-fields）与 L3137-3148（pin-option） */
.memo-fields {
  grid-template-columns: 140px minmax(0, 1fr);
}

.pin-option {
  display: flex !important;
  grid-template-columns: auto 1fr;
  align-items: center;
  gap: 8px;
  margin-top: 15px;
}

.pin-option input {
  width: 17px;
  height: 17px;
}
</style>
