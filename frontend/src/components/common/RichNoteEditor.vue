<script setup lang="ts">
// contenteditable 富文本编辑器 —— 平移 web-legacy/app.js 的 richEditor/applyRichCommand/
// readRich/writeRich/updateRichToolbar/initRichNotes。维持 execCommand 实现（deprecated 但功能完整）。
import { nextTick, onMounted, ref } from 'vue'
import { looksLikeRichHtml, markNoteSlots, sanitizeRichHtml, escapeHtml } from '../../utils/note'

const props = withDefaults(
  defineProps<{
    modelValue: string
    placeholder?: string
    withTemplate?: boolean
  }>(),
  { placeholder: '记一句…', withTemplate: false },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'paste-image', files: File[]): void
  (e: 'template'): void
}>()

const editorRef = ref<HTMLElement | null>(null)
const isEmpty = ref(true)

const toolbarButtons = [
  { command: 'bold', label: '加粗' },
  { command: 'list', label: '列表' },
  { command: 'title', label: '标题' },
  { command: 'large', label: '大' },
  { command: 'body', label: '正文' },
]

// 命令按钮的 is-active 状态（bold/list 用 queryCommandState，其余按当前块判断）
const activeCommands = ref<Record<string, boolean>>({})

function syncEmpty() {
  const editor = editorRef.value
  if (!editor) return
  isEmpty.value = !editor.innerText.replace(/ /g, ' ').trim()
}

function readRich(): string {
  const editor = editorRef.value
  if (!editor || !editor.innerText.replace(/ /g, ' ').trim()) return ''
  return sanitizeRichHtml(editor.innerHTML)
}

function writeRich(content: string) {
  const editor = editorRef.value
  if (!editor) return
  if (!content) {
    editor.innerHTML = ''
  } else if (looksLikeRichHtml(content)) {
    editor.innerHTML = sanitizeRichHtml(content)
  } else {
    editor.innerHTML = String(content)
      .split('\n')
      .map((line) => `<p>${escapeHtml(line) || '<br>'}</p>`)
      .join('')
  }
  syncEmpty()
}

function richBlock(): HTMLElement | null {
  const editor = editorRef.value
  const selection = window.getSelection()
  if (!editor || !selection?.rangeCount) return null
  let node = selection.anchorNode as Node | null
  if (!node || !editor.contains(node)) return null
  if (node.nodeType === Node.TEXT_NODE) node = node.parentNode
  while (node && node !== editor && !['P', 'H3', 'LI', 'DIV'].includes((node as HTMLElement).tagName)) {
    node = node.parentNode
  }
  return node && node !== editor ? (node as HTMLElement) : null
}

function applyCommand(command: string) {
  const editor = editorRef.value
  if (!editor) return
  editor.focus()
  if (command === 'bold') {
    document.execCommand('bold')
  } else if (command === 'list') {
    document.execCommand('insertUnorderedList')
  } else if (command === 'title') {
    document.execCommand('formatBlock', false, 'h3')
    richBlock()?.classList.remove('note-lg')
  } else if (command === 'large' || command === 'body') {
    document.execCommand('formatBlock', false, 'p')
    const block = richBlock()
    if (!block) return
    block.classList.remove('note-lg', 'note-title')
    if (command === 'large') block.classList.add('note-lg')
  }
  syncEmpty()
  emitValue()
  updateToolbar()
}

function updateToolbar() {
  const block = richBlock()
  const next: Record<string, boolean> = {}
  try {
    next.bold = document.queryCommandState('bold')
  } catch {
    next.bold = false
  }
  try {
    next.list = document.queryCommandState('insertUnorderedList')
  } catch {
    next.list = false
  }
  next.title = block?.tagName === 'H3'
  next.large = Boolean(block?.classList.contains('note-lg'))
  next.body = Boolean(block && block.tagName !== 'H3' && !block.classList.contains('note-lg'))
  activeCommands.value = next
}

function emitValue() {
  emit('update:modelValue', readRich())
}

function onPaste(event: ClipboardEvent) {
  const files = [...(event.clipboardData?.items ?? [])]
    .filter((item) => item.type.startsWith('image/'))
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file))
  if (files.length) {
    event.preventDefault()
    emit('paste-image', files)
    return
  }
  const text = event.clipboardData?.getData('text/plain')
  if (!text) return
  event.preventDefault()
  document.execCommand('insertText', false, text)
  syncEmpty()
  emitValue()
}

function onEditorClick(event: MouseEvent) {
  const editor = editorRef.value
  const slot = (event.target as HTMLElement).closest('.note-slot')
  if (!editor || !slot || !editor.contains(slot)) return
  const range = document.createRange()
  range.selectNodeContents(slot)
  const selection = window.getSelection()
  selection?.removeAllRanges()
  selection?.addRange(range)
}

function onToolbarMousedown(event: MouseEvent) {
  if ((event.target as HTMLElement).closest('button')) event.preventDefault()
}

function onToolbarClick(event: MouseEvent) {
  const button = (event.target as HTMLElement).closest('[data-command]') as HTMLElement | null
  if (!button) return
  if (button.dataset.command === 'template') {
    emit('template')
    return
  }
  applyCommand(button.dataset.command ?? '')
}

/** 模板插入（平移 insertTemplate）：模板对话框回调查这个 */
function insertTemplateContent(content: string) {
  const editor = editorRef.value
  if (!editor) return
  const incoming = document.createElement('div')
  incoming.innerHTML = looksLikeRichHtml(content)
    ? sanitizeRichHtml(content)
    : String(content || '')
        .split('\n')
        .map((line) => `<p>${escapeHtml(line) || '<br>'}</p>`)
        .join('')
  markNoteSlots(incoming)
  const empty = !editor.innerText.replace(/ /g, ' ').trim()
  if (empty) editor.replaceChildren()
  else {
    const gap = document.createElement('p')
    gap.append(document.createElement('br'))
    editor.append(gap)
  }
  while (incoming.firstChild) editor.append(incoming.firstChild)
  const slot = editor.querySelector('.note-slot')
  editor.focus()
  if (slot) {
    const range = document.createRange()
    range.selectNodeContents(slot)
    const selection = window.getSelection()
    selection?.removeAllRanges()
    selection?.addRange(range)
  }
  syncEmpty()
  emitValue()
}

defineExpose({ insertTemplateContent, readRich, writeRich })

onMounted(async () => {
  try {
    document.execCommand('defaultParagraphSeparator', false, 'p')
  } catch {
    // 个别浏览器不支持默认段落，回车仍然可以换行。
  }
  await nextTick()
  writeRich(props.modelValue)
  syncEmpty()
})
</script>

<template>
  <div class="rich-note">
    <div class="rich-note-toolbar" @mousedown="onToolbarMousedown" @click="onToolbarClick">
      <button
        v-for="item in toolbarButtons"
        :key="item.command"
        type="button"
        :data-command="item.command"
        :class="{ 'is-active': activeCommands[item.command] }"
      >
        {{ item.label }}
      </button>
      <button v-if="withTemplate" type="button" data-command="template">模板</button>
    </div>
    <div
      ref="editorRef"
      class="rich-note-body"
      contenteditable="true"
      :class="{ 'is-empty': isEmpty }"
      :data-placeholder="placeholder"
      @input="syncEmpty(); emitValue()"
      @keyup="updateToolbar"
      @mouseup="updateToolbar"
      @click="onEditorClick"
      @paste="onPaste"
    ></div>
  </div>
</template>
