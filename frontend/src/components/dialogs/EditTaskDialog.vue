<script setup lang="ts">
// 编辑任务对话框 —— 平移 openEditDialog / saveTaskEdit / deleteTask（app.js 1775-1836）。
import { ref, watch } from 'vue'
import BaseDialog from '../common/BaseDialog.vue'
import { useDayStore } from '../../stores/day'
import { useUiStore } from '../../stores/ui'
import type { Entry } from '../../types/api'

const props = defineProps<{
  open: boolean
  entry: Entry | null
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const dayStore = useDayStore()
const ui = useUiStore()

const title = ref('')
const project = ref('')
const estimate = ref('0')
const start = ref('')
const definition = ref('')
const busy = ref(false)

watch(
  () => props.open,
  (open) => {
    if (!open || !props.entry) return
    title.value = props.entry.title
    project.value = props.entry.project_name || ''
    estimate.value = String(props.entry.estimate_minutes)
    start.value = props.entry.planned_start || ''
    definition.value = props.entry.definition || ''
  },
)

async function save() {
  if (!props.entry || busy.value) return
  busy.value = true
  try {
    await dayStore.saveTaskEdit(props.entry.id, {
      title: title.value,
      project_name: project.value,
      estimate_minutes: Number(estimate.value) || 0,
      planned_start: start.value,
      definition: definition.value,
    })
    emit('close')
    ui.notify('任务已更新')
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '保存失败', true)
  } finally {
    busy.value = false
  }
}

async function remove() {
  if (!props.entry || busy.value) return
  if (!window.confirm(`确定删除“${props.entry.title}”吗？`)) return
  busy.value = true
  try {
    await dayStore.deleteTask(props.entry.id)
    emit('close')
    ui.notify('任务已删除')
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '删除失败', true)
  } finally {
    busy.value = false
  }
}

/** 平移 saveTaskEdit：cancel 提交器直接关闭，其余走保存 */
function onSubmit(event: SubmitEvent) {
  const submitter = event.submitter as HTMLButtonElement | null
  if (submitter?.value === 'cancel') {
    emit('close')
    return
  }
  event.preventDefault()
  void save()
}
</script>

<template>
  <BaseDialog :open="open" @close="emit('close')">
    <form method="dialog" @submit="onSubmit">
      <div class="dialog-header">
        <div>
          <p class="eyebrow">调整任务</p>
          <h2>编辑任务</h2>
        </div>
        <button class="dialog-close" value="cancel" aria-label="关闭">×</button>
      </div>
      <label>
        <span>任务名称</span>
        <input v-model="title" type="text" maxlength="240" required />
      </label>
      <div class="field-row">
        <label>
          <span>项目</span>
          <input v-model="project" type="text" maxlength="80" list="projectOptions" />
        </label>
        <label>
          <span>预估分钟</span>
          <input v-model="estimate" type="number" min="0" max="1440" step="5" />
        </label>
        <label>
          <span>计划开始</span>
          <input v-model="start" type="time" />
        </label>
      </div>
      <label>
        <span>完成标准 / 补充说明</span>
        <textarea v-model="definition" rows="3" maxlength="1000"></textarea>
      </label>
      <div class="dialog-actions split-actions">
        <button type="button" class="button danger-text" :disabled="busy" @click="remove">
          删除
        </button>
        <div>
          <button class="button subtle" value="cancel">取消</button>
          <button type="submit" class="button primary" :disabled="busy">
            {{ busy ? '保存中…' : '保存' }}
          </button>
        </div>
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
</style>
