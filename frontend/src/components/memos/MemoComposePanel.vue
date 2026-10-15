<script setup lang="ts">
// 感悟快速记录面板 —— 平移 web-legacy/index.html L589-642 + app.js submitMemoCompose(2289)
import { ref } from 'vue'
import { useMemoStore } from '../../stores/memo'
import { useDialogStore } from '../../stores/dialogs'
import { todayString } from '../../utils/date'
import RichNoteEditor from '../common/RichNoteEditor.vue'
import ImageComposer from '../common/ImageComposer.vue'
import TagPresets from '../common/TagPresets.vue'

const memoStore = useMemoStore()
const dialogsStore = useDialogStore()

const richRef = ref<{
  insertTemplateContent: (content: string) => void
  writeRich: (content: string) => void
  readRich: () => string
} | null>(null)
const content = ref('')
const memoDate = ref(todayString())
const memoTags = ref('')

function templateTarget() {
  return richRef.value
    ? { insertTemplateContent: (c: string) => richRef.value?.insertTemplateContent(c) }
    : null
}

async function onSubmit() {
  const ok = await memoStore.submitMemo({
    bucket: 'compose',
    date: memoDate.value,
    content: content.value,
    tags: memoTags.value,
  })
  if (!ok) return
  // 提交成功后 store 已清空图片桶并刷新列表；这里清空编辑器与标签
  content.value = ''
  richRef.value?.writeRich('')
  memoTags.value = ''
}

defineExpose({ templateTarget })
</script>

<template>
  <section class="panel memo-compose-panel">
    <div class="panel-header compact-header">
      <div>
        <p class="eyebrow">快速记录</p>
        <h2>现在想到什么？</h2>
      </div>
    </div>
    <form class="memo-compose-form" @submit.prevent="onSubmit">
      <RichNoteEditor
        ref="richRef"
        v-model="content"
        with-template
        placeholder="一条记录只保留一个想法，以后更容易搜索和重组。也可以直接粘贴图片。"
        @template="dialogsStore.openTemplate(templateTarget())"
        @paste-image="memoStore.addFilesToBucket($event, 'compose')"
      />
      <ImageComposer
        :pending="memoStore.pendingComposeImages"
        @add-files="memoStore.addFilesToBucket($event, 'compose')"
        @remove-pending="memoStore.removePendingImage('compose', $event)"
      />
      <div class="field-row memo-fields">
        <label>
          <span>日期</span>
          <input v-model="memoDate" type="date" required />
        </label>
        <label>
          <span>标签</span>
          <input v-model="memoTags" type="text" maxlength="300" placeholder="用逗号分隔" />
          <TagPresets v-model="memoTags" tag-input-id="memoTags" />
        </label>
      </div>
      <div class="form-actions">
        <button type="submit" class="button primary">保存感悟</button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.memo-compose-panel {
  position: sticky;
  top: 94px;
}

.memo-compose-form {
  padding: 0 20px 20px;
}

.memo-fields {
  grid-template-columns: 140px minmax(0, 1fr);
}
</style>
