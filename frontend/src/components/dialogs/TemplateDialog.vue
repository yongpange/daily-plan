<script setup lang="ts">
// 感悟模板对话框 —— 平移 web-legacy/index.html L1000-1037（templateDialog）+
// app.js renderTemplates(4004) / resetTemplateForm(4030) / openTemplateDialog(4037) /
// saveTemplate(4049) / deleteTemplate(4085) / insertTemplate 使用分支(4666-4684)
// 全局挂载在 App.vue，由 dialogsStore.templateOpen/templateEditor 控制
import { nextTick, ref, watch } from 'vue'
import { useMemoStore } from '../../stores/memo'
import { useDialogStore } from '../../stores/dialogs'
import { useUiStore } from '../../stores/ui'
import BaseDialog from '../common/BaseDialog.vue'
import RichNoteEditor from '../common/RichNoteEditor.vue'

const memoStore = useMemoStore()
const dialogsStore = useDialogStore()
const ui = useUiStore()

const richRef = ref<{
  writeRich: (content: string) => void
  readRich: () => string
} | null>(null)

const templateName = ref('')
const templateContent = ref('')
const editingTemplateId = ref<number | null>(null)
const saving = ref(false)

// ---------- 表单重置（平移 resetTemplateForm） ----------
function resetTemplateForm() {
  editingTemplateId.value = null
  templateName.value = ''
  templateContent.value = ''
  saveButtonText.value = '保存模板'
  richRef.value?.writeRich('')
}

// 打开时重置表单并加载列表（平移 openTemplateDialog）
watch(
  () => dialogsStore.templateOpen,
  async (open) => {
    if (!open) return
    resetTemplateForm()
    await nextTick()
    richRef.value?.writeRich('')
    try {
      await memoStore.loadTemplates()
    } catch (error) {
      ui.notify(error instanceof Error ? error.message : '模板加载失败', true)
    }
  },
)

const saveButtonText = ref('保存模板')

// ---------- 使用 / 编辑 / 删除（平移 templateList 委托） ----------
function useTemplate(templateId: number) {
  const template = memoStore.templates.find((item) => item.id === templateId)
  if (!template) return
  dialogsStore.templateEditor?.insertTemplateContent(template.content)
  dialogsStore.closeTemplate()
}

function editTemplate(templateId: number) {
  const template = memoStore.templates.find((item) => item.id === templateId)
  if (!template) return
  editingTemplateId.value = template.id
  templateName.value = template.name
  templateContent.value = template.content
  richRef.value?.writeRich(template.content)
  saveButtonText.value = '更新模板'
}

async function deleteTemplate(templateId: number) {
  if (!window.confirm('确定删除这个模板吗？')) return
  try {
    await memoStore.deleteTemplate(templateId)
    if (editingTemplateId.value === templateId) resetTemplateForm()
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '模板删除失败', true)
  }
}

// ---------- 保存（平移 saveTemplate） ----------
async function onSave() {
  const name = templateName.value.trim()
  const content = richRef.value?.readRich() ?? templateContent.value
  if (!name) {
    ui.notify('先给模板起个名字', true)
    return
  }
  if (!content) {
    ui.notify('模板里先写一点内容', true)
    return
  }
  saving.value = true
  try {
    await memoStore.saveTemplate({
      ...(editingTemplateId.value != null ? { id: editingTemplateId.value } : {}),
      name,
      content,
    })
    resetTemplateForm()
    ui.notify('模板已保存')
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '模板保存失败', true)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <BaseDialog :open="dialogsStore.templateOpen" @close="dialogsStore.closeTemplate">
    <form id="templateForm" @submit.prevent="onSave">
      <div class="dialog-header">
        <div>
          <p class="eyebrow">先把常用结构存好</p>
          <h2>感悟模板</h2>
          <p>用【收获】这样的括号标出要填的位置。使用时点一下，直接换成自己的话。</p>
        </div>
        <button
          id="closeTemplateDialog"
          class="dialog-close"
          type="button"
          aria-label="关闭"
          @click="dialogsStore.closeTemplate"
        >
          ×
        </button>
      </div>
      <div id="templateList" class="template-list">
        <div v-for="template in memoStore.templates" :key="template.id" class="template-row">
          <strong>{{ template.name }}</strong>
          <div>
            <button type="button" @click="useTemplate(template.id)">使用</button>
            <button type="button" @click="editTemplate(template.id)">编辑</button>
            <button type="button" @click="deleteTemplate(template.id)">删除</button>
          </div>
        </div>
      </div>
      <label>
        <span>模板名称</span>
        <input
          id="templateName"
          v-model="templateName"
          type="text"
          maxlength="40"
          placeholder="例如：做完一个任务"
        />
      </label>
      <RichNoteEditor
        ref="richRef"
        v-model="templateContent"
        placeholder="例如：做成了【结果】。卡点是【卡点】。下次先做【下一步】。"
      />
      <div class="dialog-actions">
        <button id="resetTemplateForm" class="button subtle" type="button" @click="resetTemplateForm">
          清空
        </button>
        <button id="saveTemplate" type="submit" class="button primary" :disabled="saving">
          {{ saving ? '保存中…' : saveButtonText }}
        </button>
      </div>
    </form>
  </BaseDialog>
</template>

<style scoped>
/* template-list / template-row / task-note-hint 样式在 base.css（平移自 styles.css L2966-3066） */
</style>
