<script setup lang="ts">
// 右滑改期弹窗 —— 平移 moveChoices / openMovePopover / moveTaskTo（app.js 4111-4182）。
// 定位沿用 legacy 算法：fixed 弹窗，锚定触发行的右下/上沿。
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useDayStore } from '../../stores/day'
import type { Entry } from '../../types/api'
import { formatMonthDay, localDateString, nextMonday, shiftDate } from '../../utils/date'

const props = defineProps<{
  entry: Entry
  anchor: HTMLElement | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'move', targetDate: string): void
}>()

const dayStore = useDayStore()

const popoverRef = ref<HTMLElement | null>(null)
const position = ref({ left: '8px', top: '8px' })

/** 平移 moveChoices */
interface MoveChoice {
  key: string
  date: string
  label: string
}

const movePlan = computed(() => {
  const entry = props.entry
  const today = localDateString(new Date())
  const earliest = entry.plan_date < today ? today : shiftDate(entry.plan_date, 1)
  const choices: MoveChoice[] = []
  const push = (key: string, date: string, label: string) => {
    if (date < earliest || choices.some((item) => item.date === date)) return
    choices.push({ key, date, label })
  }
  if (entry.plan_date < today) push('today', today, '今天')
  push('tomorrow', shiftDate(today, 1), '明天')
  push('day-after', shiftDate(today, 2), '后天')
  push('monday', nextMonday(today), '下周一')
  return { earliest, choices }
})

const tomorrowChoice = computed(
  () => movePlan.value.choices.find((choice) => choice.key === 'tomorrow')?.date,
)

const customDate = ref('')

const moveNote = computed(() =>
  dayStore.aggregateSeconds(props.entry) > 0
    ? '任务会从这一天剪走。已经记下的工作时间仍留在原来的工作日志里。'
    : '任务会从这一天剪走，只出现在选中的那一天。',
)

function move(targetDate: string) {
  if (!targetDate) return
  emit('move', targetDate)
}

/** 平移 openMovePopover 的定位算法 */
async function place() {
  await nextTick()
  const popover = popoverRef.value
  const row = props.anchor
  if (!popover || !row) return
  row.classList.add('is-move-open')
  const rect = row.getBoundingClientRect()
  const width = popover.offsetWidth
  const height = popover.offsetHeight
  let left = rect.right - width - 12
  let top = rect.bottom + 6
  if (left < 8) left = Math.min(rect.left, window.innerWidth - width - 8)
  if (top + height > window.innerHeight - 8) top = Math.max(8, rect.top - height - 6)
  position.value = { left: `${Math.max(8, left)}px`, top: `${Math.max(8, top)}px` }
}

function onDocumentClick(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (popoverRef.value?.contains(target) || target.closest('.task-row.is-move-open')) return
  emit('close')
}

function onDocumentKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => {
  customDate.value = tomorrowChoice.value || movePlan.value.earliest
  void place()
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onDocumentKeydown)
})

onBeforeUnmount(() => {
  props.anchor?.classList.remove('is-move-open')
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>

<template>
  <div
    id="moveTaskPopover"
    ref="popoverRef"
    class="move-popover"
    :style="{ left: position.left, top: position.top }"
  >
    <p id="moveTaskTitle">{{ entry.title }}</p>
    <div id="moveTaskChoices" class="move-choices">
      <button
        v-for="choice in movePlan.choices"
        :key="choice.key"
        type="button"
        :class="{ 'is-primary': choice.key === 'tomorrow' }"
        :data-move-date="choice.date"
        @click="move(choice.date)"
      >
        {{ choice.label }} · {{ formatMonthDay(choice.date) }}
      </button>
    </div>
    <label class="move-custom">
      <span>其他日期</span>
      <input
        id="moveTaskDate"
        v-model="customDate"
        type="date"
        :min="movePlan.earliest"
        @change="move(customDate)"
      />
    </label>
    <p id="moveTaskNote" class="move-note">{{ moveNote }}</p>
  </div>
</template>

<style scoped>
.move-popover {
  position: fixed;
  z-index: 80;
  width: min(280px, calc(100vw - 24px));
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 16px 40px rgba(28, 45, 37, 0.16);
}

.move-popover p {
  margin: 0 0 8px;
  overflow: hidden;
  color: var(--ink);
  font-size: 13px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.move-choices {
  display: grid;
  gap: 6px;
}

.move-choices button,
.move-custom input {
  width: 100%;
  min-height: 36px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  text-align: left;
}

.move-choices button {
  padding: 0 10px;
  color: var(--ink);
  font-size: 13px;
  font-weight: 650;
}

.move-choices button.is-primary {
  border-color: transparent;
  color: #fff;
  background: var(--green);
}

.move-choices button:hover {
  border-color: #b7c9be;
}

.move-choices button.is-primary:hover {
  border-color: transparent;
  background: var(--green-dark);
}

.move-custom {
  display: grid;
  gap: 4px;
  margin-top: 8px;
}

.move-custom span,
.move-note {
  color: var(--muted);
  font-size: 11px;
  font-weight: 650;
}

.move-note {
  margin: 8px 0 0 !important;
  font-weight: 500;
  line-height: 1.5;
  white-space: normal;
}
</style>
