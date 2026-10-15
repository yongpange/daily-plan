<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useReminderStore } from '../../stores/reminder'
import { formatShortClock } from '../../utils/format'

const reminderStore = useReminderStore()
const dialogRef = ref<HTMLDialogElement | null>(null)

watch(
  () => reminderStore.alertOpen,
  async (open) => {
    await nextTick()
    const dialog = dialogRef.value
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  },
)

function acknowledge() {
  void reminderStore.acknowledgeOpenReminders()
}
</script>

<template>
  <dialog
    ref="dialogRef"
    class="dialog reminder-alert"
    @close="reminderStore.dismissAlert"
    @cancel="reminderStore.dismissAlert"
  >
    <form method="dialog" @submit="acknowledge">
      <div class="dialog-header">
        <h2>时间到了</h2>
        <p>你之前定下的提醒已经到点。</p>
      </div>
      <div id="reminderAlertList" class="reminder-alert-list">
        <p v-for="reminder in reminderStore.dueReminders" :key="reminder.id">
          <strong>{{ reminder.message }}</strong>
          <time>{{ formatShortClock(reminder.remind_at) }}</time>
        </p>
      </div>
      <div class="dialog-actions">
        <button type="submit" class="button primary" value="ack">知道了</button>
      </div>
    </form>
  </dialog>
</template>

<style scoped>
.reminder-alert-list {
  display: grid;
  gap: 10px;
}

.reminder-alert-list p {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fafcfb;
}

.reminder-alert-list time {
  color: var(--muted);
  font-size: 12px;
}
</style>
