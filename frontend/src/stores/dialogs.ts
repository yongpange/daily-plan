import { defineStore } from 'pinia'
import { ref } from 'vue'

/** 任务感悟对话框的打开目标（平移 state.noteTarget） */
export interface TaskNoteTarget {
  kind: 'task' | 'thread-step' | 'routine' | 'thread'
  entryId?: number
  taskId?: number
  routineId?: number
  threadId?: number
  title: string
  /** 要查看和续写的那一天。任务感悟用来筛当天已写的内容。 */
  date?: string
}

interface TemplateEditor {
  insertTemplateContent(content: string): void
}

export const useDialogStore = defineStore('dialogs', () => {
  // 任务感悟对话框（跨视图全局挂载在 App.vue）
  const taskNoteTarget = ref<TaskNoteTarget | null>(null)
  const taskNoteOpen = ref(false)

  function openTaskNote(target: TaskNoteTarget) {
    taskNoteTarget.value = target
    taskNoteOpen.value = true
  }

  function closeTaskNote() {
    taskNoteOpen.value = false
    taskNoteTarget.value = null
  }

  // 模板对话框（跨视图全局挂载；记录来源编辑器以便回插内容）
  const templateEditor = ref<TemplateEditor | null>(null)
  const templateOpen = ref(false)

  function openTemplate(editor: TemplateEditor | null) {
    templateEditor.value = editor
    templateOpen.value = true
  }

  function closeTemplate() {
    templateOpen.value = false
    templateEditor.value = null
  }

  return {
    taskNoteTarget,
    taskNoteOpen,
    openTaskNote,
    closeTaskNote,
    templateEditor,
    templateOpen,
    openTemplate,
    closeTemplate,
  }
})
