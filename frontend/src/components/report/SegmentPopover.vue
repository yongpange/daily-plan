<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Segment } from '../../types/api'
import { formatShortClock } from '../../utils/format'

const props = defineProps<{
  segment: Segment
  /** 触发块（.cal-block）的视口矩形，用于定位 */
  anchor: { left: number; top: number; right: number }
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'adjust'): void
}>()

const rootRef = ref<HTMLElement | null>(null)
const position = ref({ left: '0px', top: '0px' })

async function place() {
  await nextTick()
  const node = rootRef.value
  if (!node) return
  const width = node.offsetWidth
  const height = node.offsetHeight
  let left = props.anchor.right + 8
  let top = props.anchor.top
  if (left + width > window.innerWidth - 8) left = props.anchor.left - width - 8
  if (top + height > window.innerHeight - 8) top = window.innerHeight - height - 8
  position.value = { left: `${Math.max(8, left)}px`, top: `${Math.max(8, top)}px` }
}

onMounted(place)
watch(() => props.anchor, place)

// 点击 popover 外部（且不是 .cal-block）时关闭（平移 legacy document 点击监听）
function onDocumentClick(event: MouseEvent) {
  const node = rootRef.value
  if (node && node.contains(event.target as Node)) return
  if ((event.target as HTMLElement).closest('.cal-block')) return
  emit('close')
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick))

const weekdayNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

/** M月D日 (周X) HH:MM - HH:MM（平移 formatSegmentRange） */
const whenText = computed(() => {
  const date = new Date(props.segment.start_at)
  return `${date.getMonth() + 1}月${date.getDate()}日 (${weekdayNames[date.getDay()]}) ${formatShortClock(props.segment.start_at)} - ${formatShortClock(props.segment.end_at)}`
})

/** M月D日 HH:MM（平移 formatSegmentMoment） */
function formatMoment(value: string | null): string {
  if (!value) return '进行中'
  const day = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(
    new Date(value),
  )
  return `${day} ${formatShortClock(value)}`
}

/** 预计完成时间（平移 estimatedFinishText） */
const estimateText = computed(() => {
  const minutes = Number(props.segment.estimate_minutes || 0)
  if (!minutes) return '未设置'
  let start = new Date(props.segment.start_at)
  if (props.segment.planned_start && props.segment.plan_date) {
    const planned = new Date(
      `${props.segment.plan_date}T${String(props.segment.planned_start).slice(0, 5)}:00`,
    )
    if (!Number.isNaN(planned.getTime())) start = planned
  }
  return formatMoment(new Date(start.getTime() + minutes * 60000).toISOString())
})

const actualText = computed(() => formatMoment(props.segment.end_at))
</script>

<template>
  <div ref="rootRef" class="segment-popover" :style="position">
    <div class="segment-popover-actions">
      <button type="button" @click="emit('adjust')">调整</button>
      <button type="button" @click="emit('close')">退出</button>
    </div>
    <h3>{{ segment.title }}</h3>
    <p class="segment-popover-when">{{ whenText }}</p>
    <div class="segment-popover-meta">
      <p>预计完成时间　{{ estimateText }}</p>
      <p>实际完成时间　{{ actualText }}</p>
    </div>
  </div>
</template>

<style scoped>
.segment-popover {
  position: fixed;
  z-index: 80;
  width: min(360px, calc(100vw - 24px));
  padding: 8px 14px 16px;
  border: 0;
  border-radius: 8px;
  color: #fff;
  background: #3370ff;
  box-shadow: 0 8px 24px rgba(51, 112, 255, 0.28);
}

.segment-popover-actions {
  display: flex;
  justify-content: flex-end;
  gap: 2px;
  margin-bottom: 2px;
}

.segment-popover-actions button {
  min-height: 28px;
  padding: 0 8px;
  border: 0;
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.92);
  background: transparent;
  font-size: 13px;
}

.segment-popover-actions button:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.16);
}

.segment-popover h3 {
  margin: 0 0 8px;
  color: #fff;
  font-size: 20px;
  font-weight: 650;
  line-height: 1.35;
}

.segment-popover-when {
  margin: 0 0 14px;
  color: rgba(255, 255, 255, 0.9);
  font-size: 13px;
  line-height: 1.5;
}

.segment-popover-meta {
  display: grid;
  gap: 2px;
}

.segment-popover-meta p {
  margin: 0;
  color: #fff;
  font-size: 13px;
  line-height: 1.7;
}
</style>
