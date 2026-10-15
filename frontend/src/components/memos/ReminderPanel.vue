<script setup lang="ts">
// 提醒面板 —— 平移 web-legacy/index.html L645-666 + app.js prepareReminderForm(3649) /
// reminderStamp(3657) / formatReminderWhen(3661) / renderReminders(3679) /
// submitReminder(3774) / saveReminderEdit(3802) / deleteReminder(3821) / acknowledgeReminder(3838)
import { computed, onMounted, ref } from 'vue'
import type { Reminder } from '../../types/api'
import { useReminderStore } from '../../stores/reminder'
import { useUiStore } from '../../stores/ui'
import { localDateString, parseLocalDate, shiftDate } from '../../utils/date'
import { localMinute } from '../../utils/format'

const reminderStore = useReminderStore()
const ui = useUiStore()

const message = ref('')
const reminderDate = ref('')
const reminderTime = ref('')

// ---------- 表单初值：下一个整点（平移 prepareReminderForm） ----------
function prepareReminderForm() {
  const next = new Date()
  next.setMinutes(0, 0, 0)
  next.setHours(next.getHours() + 1)
  reminderDate.value = localDateString(next)
  reminderTime.value = `${String(next.getHours()).padStart(2, '0')}:${String(next.getMinutes()).padStart(2, '0')}`
}

onMounted(prepareReminderForm)

// ---------- 到期判断（平移 reminderStamp + renderReminders 的 due） ----------
function reminderStamp(reminder: Reminder): string {
  return `${reminder.remind_at.slice(0, 10)}T${reminder.remind_at.slice(11, 16)}`
}

function isDue(reminder: Reminder): boolean {
  return reminder.status === 'pending' && reminderStamp(reminder) <= localMinute()
}

// ---------- 时间文案（平移 formatReminderWhen） ----------
function formatReminderWhen(value: string): string {
  const date = value.slice(0, 10)
  const time = value.slice(11, 16)
  const today = localDateString(new Date())
  let day = date
  if (date === today) day = '今天'
  else if (date === shiftDate(today, 1)) day = '明天'
  else if (date === shiftDate(today, -1)) day = '昨天'
  else {
    day = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(
      parseLocalDate(date),
    )
  }
  return `${day} ${time}`
}

const pendingCount = computed(
  () => reminderStore.reminders.filter((item) => item.status === 'pending').length,
)
const reminderCount = computed(() => (pendingCount.value ? `${pendingCount.value} 个待提醒` : ''))

// ---------- 新增（平移 submitReminder） ----------
async function onSubmit() {
  const text = message.value.trim()
  if (!text || !reminderDate.value || !reminderTime.value) {
    ui.notify('先写下内容，并选好日期和时间', true)
    return
  }
  try {
    await reminderStore.submitReminder({
      message: text,
      remind_at: `${reminderDate.value}T${reminderTime.value}`,
    })
    message.value = ''
    prepareReminderForm()
    requestReminderPermission()
    ui.notify('提醒已设好')
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '提醒保存失败', true)
  }
}

function requestReminderPermission() {
  if (typeof Notification === 'undefined' || Notification.permission !== 'default') return
  try {
    void Notification.requestPermission()
  } catch {
    // 浏览器不允许时，页面里的提醒框仍然可用（平移 legacy 注释）
  }
}

// ---------- 编辑（平移 renderReminders 的 reminder-edit 分支 + saveReminderEdit） ----------
const editingReminderId = ref<number | null>(null)
const editMessage = ref('')
const editDate = ref('')
const editTime = ref('')

function startEdit(reminder: Reminder) {
  const [date, time] = reminder.remind_at.split('T')
  editingReminderId.value = reminder.id
  editMessage.value = reminder.message
  editDate.value = date
  editTime.value = time.slice(0, 5)
}

function cancelEdit() {
  editingReminderId.value = null
}

async function onSaveEdit() {
  if (editingReminderId.value == null) return
  try {
    await reminderStore.saveReminderEdit(editingReminderId.value, {
      message: editMessage.value.trim(),
      remind_at: `${editDate.value}T${editTime.value}`,
    })
    editingReminderId.value = null
    ui.notify('提醒已更新')
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '提醒更新失败', true)
  }
}

// ---------- 删除 / 确认（平移 deleteReminder / acknowledgeReminder） ----------
async function onDelete(reminder: Reminder) {
  if (!window.confirm('确定删掉这个提醒吗？')) return
  try {
    await reminderStore.deleteReminder(reminder.id)
    if (editingReminderId.value === reminder.id) editingReminderId.value = null
    ui.notify('提醒已删除')
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '提醒删除失败', true)
  }
}

async function onAcknowledge(reminder: Reminder) {
  try {
    await reminderStore.acknowledgeReminder(reminder.id)
  } catch (error) {
    ui.notify(error instanceof Error ? error.message : '操作失败', true)
  }
}
</script>

<template>
  <section class="panel reminder-panel">
    <div class="panel-header compact-header">
      <div>
        <p class="eyebrow">到点再看</p>
        <h2>提醒</h2>
      </div>
      <span id="reminderCount" class="autosave-label">{{ reminderCount }}</span>
    </div>
    <form id="reminderForm" class="reminder-form" @submit.prevent="onSubmit">
      <input
        id="reminderMessage"
        v-model="message"
        type="text"
        maxlength="200"
        required
        placeholder="提醒我什么，例如：给供应商回信"
      />
      <input id="reminderDate" v-model="reminderDate" type="date" required aria-label="提醒日期" />
      <input id="reminderTime" v-model="reminderTime" type="time" required aria-label="提醒时间" />
      <button type="submit" class="button primary">添加提醒</button>
    </form>
    <div id="reminderList" class="reminder-list">
      <p v-if="!reminderStore.reminders.length" class="reminder-empty">
        还没有提醒。选一个时间和一句话，到点会响。
      </p>
      <template v-for="reminder in reminderStore.reminders" :key="reminder.id">
        <form
          v-if="editingReminderId === reminder.id"
          class="reminder-edit"
          @submit.prevent="onSaveEdit"
        >
          <input v-model="editMessage" name="message" type="text" maxlength="200" required />
          <input v-model="editDate" name="date" type="date" required aria-label="提醒日期" />
          <input v-model="editTime" name="time" type="time" required aria-label="提醒时间" />
          <div class="reminder-edit-actions">
            <button type="submit" class="button primary compact">保存</button>
            <button type="button" class="button subtle compact" @click="cancelEdit">取消</button>
          </div>
        </form>
        <article
          v-else
          class="reminder-card"
          :class="{ 'is-due': isDue(reminder), 'is-done': reminder.status === 'done' }"
        >
          <time>{{ formatReminderWhen(reminder.remind_at) }}</time>
          <p>{{ reminder.message }}</p>
          <div class="reminder-actions">
            <button v-if="isDue(reminder)" type="button" @click="onAcknowledge(reminder)">
              知道了
            </button>
            <button type="button" @click="startEdit(reminder)">编辑</button>
            <button type="button" @click="onDelete(reminder)">删除</button>
          </div>
        </article>
      </template>
    </div>
  </section>
</template>

<style scoped>
/* 平移 web-legacy/styles.css L2276-2370（reminder-*） */
.autosave-label {
  color: #89938e;
  font-size: 10px;
}

.reminder-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 148px 112px auto;
  gap: 8px;
  padding: 0 20px 16px;
}

.reminder-form input {
  min-width: 0;
}

.reminder-list {
  display: grid;
  gap: 8px;
  max-height: 320px;
  padding: 0 20px 18px;
  overflow: auto;
}

.reminder-empty {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}

.reminder-card,
.reminder-edit {
  display: grid;
  gap: 4px 10px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fff;
}

.reminder-card {
  grid-template-columns: 112px minmax(0, 1fr) auto;
  align-items: center;
}

.reminder-card time {
  color: var(--green-dark);
  font-size: 13px;
  font-weight: 750;
}

.reminder-card p {
  margin: 0;
  font-size: 14px;
}

.reminder-card.is-due {
  border-color: #e4c56a;
  background: var(--yellow-soft);
}

.reminder-card.is-done {
  opacity: 0.62;
}

.reminder-card.is-done time::after {
  content: ' · 已提醒';
  color: var(--muted);
  font-weight: 650;
}

.reminder-actions,
.reminder-edit-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}

.reminder-actions button,
.reminder-edit-actions button {
  min-height: 28px;
  padding: 0 8px;
  border: 0;
  border-radius: 999px;
  color: var(--green);
  background: transparent;
  font-size: 12px;
  font-weight: 750;
  cursor: pointer;
}

.reminder-edit {
  grid-template-columns: minmax(0, 1fr);
}

.reminder-edit input {
  min-width: 0;
}
</style>
