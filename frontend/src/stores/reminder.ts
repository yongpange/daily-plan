import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as remindersApi from '../api/reminders'
import type { Reminder } from '../types/api'
import { playTone } from './ui'

export const useReminderStore = defineStore('reminder', () => {

  const reminders = ref<Reminder[]>([])
  /** 已弹窗提醒过的 id（防重复弹窗） */
  const alertedIds = new Set<number>()
  /** 到期提醒（待确认），由 ReminderAlert 对话框消费 */
  const dueReminders = ref<Reminder[]>([])
  const alertOpen = ref(false)

  let pollHandle: number | undefined

  async function refreshReminders() {
    try {
      const data = await remindersApi.fetchReminders()
      reminders.value = data
      notifyDueReminders()
    } catch {
      // 轮询失败静默（平移 refreshReminders 的唯一静默 catch）
    }
  }

  function notifyDueReminders() {
    const nowIso = new Date().toISOString()
    const due = reminders.value.filter(
      (reminder) => reminder.status === 'pending' && reminder.remind_at <= nowIso && !alertedIds.has(reminder.id),
    )
    if (!due.length) return
    due.forEach((reminder) => alertedIds.add(reminder.id))
    dueReminders.value = due
    alertOpen.value = true
    playTone()
    requestNotificationPermission()
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      due.forEach((reminder) => {
        try {
          new Notification('每日计划提醒', { body: reminder.message })
        } catch {
          // 通知失败不影响弹窗
        }
      })
    }
  }

  function requestNotificationPermission() {
    if (typeof Notification === 'undefined') return
    if (Notification.permission === 'default') {
      void Notification.requestPermission()
    }
  }

  /** 15s 轮询 + 回前台立即刷新（由 App 启动/visibilitychange 调用） */
  function startPolling() {
    if (pollHandle !== undefined) return
    void refreshReminders()
    pollHandle = window.setInterval(() => {
      void refreshReminders()
    }, 15000)
    document.addEventListener('visibilitychange', onVisibilityChange)
  }

  function onVisibilityChange() {
    if (!document.hidden) void refreshReminders()
  }

  function stopPolling() {
    window.clearInterval(pollHandle)
    pollHandle = undefined
    document.removeEventListener('visibilitychange', onVisibilityChange)
  }

  async function submitReminder(payload: { message: string; remind_at: string }) {
    await remindersApi.createReminder(payload)
    await refreshReminders()
  }

  async function saveReminderEdit(reminderId: number, payload: { message?: string; remind_at?: string }) {
    await remindersApi.updateReminder(reminderId, payload)
    await refreshReminders()
  }

  async function deleteReminder(reminderId: number) {
    await remindersApi.deleteReminder(reminderId)
    await refreshReminders()
  }

  async function acknowledgeReminder(reminderId: number) {
    await remindersApi.updateReminder(reminderId, { status: 'done' })
    await refreshReminders()
  }

  async function acknowledgeOpenReminders() {
    const open = reminders.value.filter((reminder) => reminder.status === 'pending')
    for (const reminder of open) {
      await remindersApi.updateReminder(reminder.id, { status: 'done' })
    }
    alertOpen.value = false
    dueReminders.value = []
    await refreshReminders()
  }

  function dismissAlert() {
    alertOpen.value = false
    dueReminders.value = []
  }

  return {
    reminders,
    dueReminders,
    alertOpen,
    refreshReminders,
    startPolling,
    stopPolling,
    submitReminder,
    saveReminderEdit,
    deleteReminder,
    acknowledgeReminder,
    acknowledgeOpenReminders,
    dismissAlert,
  }
})
