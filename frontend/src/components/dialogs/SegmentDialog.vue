<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import BaseDialog from '../common/BaseDialog.vue'
import { errorMessage } from '../../api/http'
import { deleteSegment, updateSegment } from '../../api/timers'
import { useReportStore } from '../../stores/report'
import { useUiStore } from '../../stores/ui'
import type { Segment } from '../../types/api'
import { formatShortClock } from '../../utils/format'

const props = defineProps<{
  open: boolean
  segment: Segment | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const reportStore = useReportStore()
const ui = useUiStore()

const duration = ref('60')
const busy = ref(false)

watch(
  () => props.open,
  (open) => {
    if (open && props.segment) {
      duration.value = String(
        Math.max(1, Math.round(Number(props.segment.duration_seconds || 0) / 60)),
      )
    }
  },
)

const taskName = computed(() =>
  props.segment
    ? `${props.segment.title} · ${formatShortClock(props.segment.start_at)}–${formatShortClock(props.segment.end_at)}`
    : '',
)

async function save() {
  if (!props.segment || busy.value) return
  busy.value = true
  try {
    await updateSegment(props.segment.id, Number(duration.value))
    emit('close')
    await reportStore.loadDayDetail()
    ui.notify('工作记录已修正')
  } catch (error) {
    ui.notify(errorMessage(error), true)
  } finally {
    busy.value = false
  }
}

async function remove() {
  if (!props.segment || busy.value) return
  if (!window.confirm('确定删除这段工作记录吗？')) return
  busy.value = true
  try {
    await deleteSegment(props.segment.id)
    emit('close')
    await reportStore.loadDayDetail()
    ui.notify('工作记录已删除')
  } catch (error) {
    ui.notify(errorMessage(error), true)
  } finally {
    busy.value = false
  }
}

/** 平移 saveSegmentEdit：cancel 提交器直接关闭，其余走保存 */
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
          <p class="eyebrow">只在误操作时修正</p>
          <h2>调整工作记录</h2>
          <p>{{ taskName }}</p>
        </div>
        <button class="dialog-close" value="cancel" aria-label="关闭">×</button>
      </div>
      <label>
        <span>有效工作分钟</span>
        <input
          v-model="duration"
          type="number"
          min="1"
          max="1440"
          step="1"
          required
        />
      </label>
      <div class="dialog-actions split-actions">
        <button type="button" class="button danger-text" :disabled="busy" @click="remove">
          删除这段
        </button>
        <div>
          <button class="button subtle" value="cancel">取消</button>
          <button type="submit" class="button primary" :disabled="busy">保存修正</button>
        </div>
      </div>
    </form>
  </BaseDialog>
</template>
