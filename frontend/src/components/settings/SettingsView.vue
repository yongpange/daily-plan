<script setup lang="ts">
import { onMounted } from 'vue'
import { errorMessage } from '../../api/http'
import { useSettingsStore } from '../../stores/settings'
import { useRoutineStore } from '../../stores/routine'
import { useUiStore } from '../../stores/ui'
import ProfileForm from './ProfileForm.vue'
import RoutineSettings from './RoutineSettings.vue'

const settingsStore = useSettingsStore()
const routineStore = useRoutineStore()
const ui = useUiStore()

// 平移 loadSettings：设置页数据（profile + routines）
onMounted(async () => {
  const data = await settingsStore.loadSettings().catch((error: unknown) => {
    ui.notify(errorMessage(error), true)
    return null
  })
  if (data) routineStore.setRoutines(data.routines)
})
</script>

<template>
  <div class="view-toolbar">
    <div>
      <p class="eyebrow">只在这里改承诺</p>
      <h1>设置</h1>
    </div>
  </div>
  <div class="settings-layout">
    <div class="settings-side">
      <section class="panel">
        <div class="panel-header compact-header">
          <div>
            <p class="eyebrow">个人资料</p>
            <h2>你是谁</h2>
          </div>
        </div>
        <ProfileForm />
      </section>
    </div>
    <RoutineSettings />
  </div>
</template>

<style scoped>
.settings-layout {
  display: grid;
  grid-template-columns: minmax(320px, 380px) minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

.settings-side .panel > .panel-header {
  padding-right: 28px;
  padding-left: 28px;
}

@media (max-width: 980px) {
  .settings-layout {
    grid-template-columns: 1fr;
  }

  .settings-side .panel > .panel-header {
    padding-right: 20px;
    padding-left: 20px;
  }
}
</style>
