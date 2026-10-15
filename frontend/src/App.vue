<script setup lang="ts">
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from './components/layout/AppHeader.vue'
import RunningBar from './components/layout/RunningBar.vue'
import BreakBar from './components/layout/BreakBar.vue'
import Toast from './components/layout/Toast.vue'
import ImageViewer from './components/dialogs/ImageViewer.vue'
import ReminderAlert from './components/dialogs/ReminderAlert.vue'
import TaskNoteDialog from './components/dialogs/TaskNoteDialog.vue'
import TemplateDialog from './components/dialogs/TemplateDialog.vue'
import { errorMessage } from './api/http'
import { useTimerStore } from './stores/timer'
import { useReminderStore } from './stores/reminder'
import { useDayStore } from './stores/day'
import { useReportStore } from './stores/report'
import { useMemoStore } from './stores/memo'
import { useSettingsStore } from './stores/settings'
import { useUiStore } from './stores/ui'

const route = useRoute()
const timerStore = useTimerStore()
const reminderStore = useReminderStore()
const dayStore = useDayStore()
const reportStore = useReportStore()
const memoStore = useMemoStore()
const settingsStore = useSettingsStore()
const ui = useUiStore()

// 平移 switchView：按路由加载对应数据
watch(
  () => route.name,
  async (name) => {
    if (name === 'today') await dayStore.loadDay().catch((e) => ui.notify(errorMessage(e), true))
    if (name === 'report') await reportStore.loadReport().catch((e) => ui.notify(errorMessage(e), true))
    if (name === 'memos') {
      await Promise.all([
        memoStore.loadMemos().catch((e) => ui.notify(errorMessage(e), true)),
        reminderStore.refreshReminders(),
        timerStore.refreshGlobalTimer().catch((e) => ui.notify(errorMessage(e), true)),
      ])
      await memoStore.loadSuggestedTags().catch(() => {})
    }
    if (name === 'settings') {
      await settingsStore.loadSettings().catch((e) => ui.notify(errorMessage(e), true))
    }
  },
  { immediate: true },
)

onMounted(() => {
  timerStore.startTicking()
  reminderStore.startPolling()
})

onBeforeUnmount(() => {
  timerStore.stopTicking()
  reminderStore.stopPolling()
})
</script>

<template>
  <AppHeader />
  <RunningBar />
  <BreakBar />
  <main class="page-shell">
    <RouterView />
  </main>
  <Toast />
  <ImageViewer />
  <ReminderAlert />
  <TaskNoteDialog />
  <TemplateDialog />
</template>
