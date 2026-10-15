<script setup lang="ts">
// 专注对话框 —— 平移 openFocusDialog / updateFocusPresets / submitFocus（app.js 1665-1705）。
// 确认后 startTimer({entryId, mode:'focus', focusMinutes}) 并持久化 focus/break 分钟。
import { ref, watch } from 'vue'
import BaseDialog from '../common/BaseDialog.vue'
import { useTimerStore } from '../../stores/timer'
import type { Entry } from '../../types/api'
import { safeStorageGet, safeStorageSet, STORAGE } from '../../utils/storage'

const props = defineProps<{
  open: boolean
  entry: Entry | null
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const timerStore = useTimerStore()

const focusMinutes = ref(25)
const breakMinutes = ref(5)
const busy = ref(false)

const presets = [
  { minutes: 25, label: '短专注' },
  { minutes: 50, label: '深度工作' },
  { minutes: 90, label: '长任务' },
]

watch(
  () => props.open,
  (open) => {
    if (!open) return
    focusMinutes.value = Number(safeStorageGet(STORAGE.focusMinutes) || 25)
    breakMinutes.value = Number(safeStorageGet(STORAGE.breakMinutes) || 5)
  },
)

/** 平移 updateFocusPresets */
function isPresetActive(minutes: number): boolean {
  return Number(minutes) === Number(focusMinutes.value)
}

function pickPreset(minutes: number) {
  focusMinutes.value = minutes
}

async function start() {
  if (!props.entry || busy.value) return
  busy.value = true
  try {
    safeStorageSet(STORAGE.focusMinutes, focusMinutes.value)
    safeStorageSet(STORAGE.breakMinutes, breakMinutes.value)
    emit('close')
    await timerStore.startTimer({
      entryId: props.entry.id,
      mode: 'focus',
      focusMinutes: focusMinutes.value,
    })
  } finally {
    busy.value = false
  }
}

/** 平移 submitFocus：cancel 提交器直接关闭，其余开始专注 */
function onSubmit(event: SubmitEvent) {
  const submitter = event.submitter as HTMLButtonElement | null
  if (submitter?.value === 'cancel') {
    emit('close')
    return
  }
  event.preventDefault()
  void start()
}
</script>

<template>
  <BaseDialog :open="open" @close="emit('close')">
    <form method="dialog" @submit="onSubmit">
      <div class="dialog-header">
        <div>
          <p class="eyebrow">可选的番茄专注</p>
          <h2>开始一个专注段</h2>
          <p id="focusTaskName">{{ entry?.title }}</p>
        </div>
        <button class="dialog-close" value="cancel" aria-label="关闭">×</button>
      </div>
      <div class="focus-presets">
        <button
          v-for="preset in presets"
          :key="preset.minutes"
          type="button"
          :data-focus-minutes="preset.minutes"
          :class="{ 'is-active': isPresetActive(preset.minutes) }"
          @click="pickPreset(preset.minutes)"
        >
          <strong>{{ preset.minutes }}</strong>
          <span>{{ preset.label }}</span>
        </button>
      </div>
      <div class="field-row focus-fields">
        <label>
          <span>专注分钟</span>
          <input v-model.number="focusMinutes" type="number" min="5" max="180" />
        </label>
        <label>
          <span>完成后休息</span>
          <input v-model.number="breakMinutes" type="number" min="1" max="60" />
        </label>
      </div>
      <p class="dialog-hint">
        提前结束仍会计入实际工作时间；完成整段才会计入专注完成数。
      </p>
      <div class="dialog-actions">
        <button class="button subtle" value="cancel">取消</button>
        <button type="submit" class="button primary" :disabled="busy">
          {{ busy ? '准备专注…' : '开始专注' }}
        </button>
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

.focus-presets {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 9px;
}

.focus-presets button {
  display: grid;
  gap: 3px;
  min-height: 90px;
  place-content: center;
  border: 1px solid var(--line);
  border-radius: 12px;
  color: var(--muted);
  background: #fafcfb;
}

.focus-presets button strong {
  color: var(--ink);
  font-size: 27px;
}

.focus-presets button span {
  font-size: 10px;
}

.focus-presets button.is-active {
  border-color: #9589c4;
  background: #f1eef9;
}

.focus-fields {
  grid-template-columns: 1fr 1fr;
}

.dialog-hint {
  margin: 16px 0 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.6;
}
</style>
