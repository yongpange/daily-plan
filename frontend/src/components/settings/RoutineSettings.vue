<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { errorMessage } from '../../api/http'
import { useRoutineStore } from '../../stores/routine'
import { useUiStore } from '../../stores/ui'
import { formatMinutes } from '../../utils/format'
import RoutineGateDialog from './RoutineGateDialog.vue'

const routineStore = useRoutineStore()
const ui = useUiStore()

// 平移 renderRoutineSettings 的锁定逻辑：有必做且未解锁时锁定
const locked = computed(() => routineStore.routines.length > 0 && !routineStore.unlockToken)
const unlocked = computed(() => Boolean(routineStore.unlockToken))

// 卡片草稿（解锁后可编辑）
const drafts = reactive<Record<number, { title: string; note: string; estimate: number }>>({})

watch(unlocked, (open) => {
  if (!open) return
  for (const routine of routineStore.routines) {
    drafts[routine.id] = {
      title: routine.title,
      note: routine.note || '',
      estimate: Number(routine.estimate_minutes) || 0,
    }
  }
})

const gateOpen = ref(false)
const newTitle = ref('')
const newNote = ref('')
const newEstimate = ref(5)
const creating = ref(false)
const savingCard = ref<number | null>(null)

async function openGate() {
  await routineStore.openRoutineGate().catch((error: unknown) => {
    ui.notify(errorMessage(error), true)
  })
  if (routineStore.challenge) gateOpen.value = true
}

// 平移 createRoutine
async function onCreate() {
  creating.value = true
  try {
    await routineStore.createRoutine({
      title: newTitle.value,
      note: newNote.value,
      estimate_minutes: Number(newEstimate.value) || 0,
    })
    newTitle.value = ''
    newNote.value = ''
    newEstimate.value = 5
    ui.notify('每日必做已添加，从今天开始出现')
  } catch (error) {
    ui.notify(errorMessage(error), true)
  } finally {
    creating.value = false
  }
}

// 平移 saveRoutineCard
async function onSaveCard(id: number) {
  const draft = drafts[id]
  if (!draft) return
  savingCard.value = id
  try {
    await routineStore.saveRoutineCard(id, {
      title: draft.title,
      note: draft.note,
      estimate_minutes: Number(draft.estimate) || 0,
    })
    ui.notify('每日必做已更新')
  } catch (error) {
    ui.notify(errorMessage(error), true)
  } finally {
    savingCard.value = null
  }
}

// 平移 deleteRoutineCard
async function onDeleteCard(id: number) {
  const draft = drafts[id]
  const title = draft?.title ?? routineStore.routines.find((item) => item.id === id)?.title ?? ''
  if (!window.confirm(`确定删除每日必做“${title}”吗？已有打卡记录仍会留在复盘里。`)) {
    return
  }
  try {
    await routineStore.deleteRoutineCard(id)
    ui.notify('每日必做已删除')
  } catch (error) {
    ui.notify(errorMessage(error), true)
  }
}
</script>

<template>
  <section class="panel routine-settings-panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">每日必做</p>
        <h2>设好之后，每天都会出现</h2>
      </div>
      <button v-if="locked" id="unlockRoutines" class="button dark compact" type="button" @click="openGate">
        修改每日必做
      </button>
    </div>
    <p class="routine-guard-note">
      这些任务使用专属颜色。首页只能打卡；改掉或删除已经生效的项目，要先答对 3 道包含加减乘除的题。
    </p>
    <p v-if="unlocked" class="routine-unlock-note">修改已开启。这段时间结束后会重新锁定。</p>
    <div id="routineSettingsList" class="routine-settings-list">
      <div v-if="!routineStore.routines.length" class="routine-empty">
        例如：每天锻炼 5 分钟，每天看飞书里的 5 篇生财有术文章。已经生效的项目，改掉或删除前要先答对 3 道题。
      </div>
      <template v-else-if="locked">
        <article v-for="routine in routineStore.routines" :key="routine.id" class="routine-setting-card"
          :style="{ '--routine': routine.color } as Record<string, string>">
          <strong class="routine-title">{{ routine.title }}</strong>
          <div class="routine-meta">
            <span v-if="routine.note">{{ routine.note }}</span>
            <span>{{ routine.estimate_minutes ? formatMinutes(routine.estimate_minutes) : '不计入预估' }}</span>
            <span>已锁定</span>
          </div>
        </article>
      </template>
      <template v-else>
        <article v-for="routine in routineStore.routines" :key="routine.id" class="routine-setting-card"
          :data-routine-id="routine.id" :style="{ '--routine': routine.color } as Record<string, string>">
          <label>
            <span>必做事项</span>
            <input v-model="drafts[routine.id].title" data-field="title" type="text" maxlength="80" />
          </label>
          <div class="field-row">
            <label>
              <span>补充说明</span>
              <input v-model="drafts[routine.id].note" data-field="note" type="text" maxlength="200" />
            </label>
            <label>
              <span>预估分钟</span>
              <input v-model.number="drafts[routine.id].estimate" data-field="estimate" type="number" min="0" max="240" step="5" />
            </label>
          </div>
          <div class="form-actions">
            <button type="button" class="button danger-text" data-routine-action="delete"
              @click="onDeleteCard(routine.id)">
              删除
            </button>
            <button type="button" class="button primary" data-routine-action="save" :disabled="savingCard === routine.id"
              @click="onSaveCard(routine.id)">
              {{ savingCard === routine.id ? '保存中…' : '保存这项' }}
            </button>
          </div>
        </article>
      </template>
    </div>
    <form id="routineCreateForm" class="routine-create-form" @submit.prevent="onCreate">
      <label>
        <span>必做事项</span>
        <input id="routineTitle" v-model="newTitle" type="text" maxlength="80" placeholder="例如：锻炼、阅读生财有术文章"
          required />
      </label>
      <div class="field-row">
        <label>
          <span>补充说明</span>
          <input id="routineNote" v-model="newNote" type="text" maxlength="200" placeholder="例如：看飞书里的 5 篇" />
        </label>
        <label>
          <span>预估分钟</span>
          <input id="routineEstimate" v-model.number="newEstimate" type="number" min="0" max="240" step="5" />
        </label>
      </div>
      <div class="form-actions">
        <button type="submit" class="button primary" :disabled="creating">
          {{ creating ? '添加中…' : '添加每日必做' }}
        </button>
      </div>
    </form>
    <RoutineGateDialog :open="gateOpen" @close="gateOpen = false" />
  </section>
</template>

<style scoped>
.routine-guard-note,
.routine-unlock-note {
  margin: 0 0 14px;
  color: #8a5a12;
  font-size: 12px;
  line-height: 1.6;
}

.routine-unlock-note {
  padding: 8px 10px;
  border-radius: 8px;
  background: #fff4d9;
}

.routine-settings-list {
  display: grid;
  gap: 10px;
  padding-bottom: 4px;
}

.routine-setting-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  padding: 12px;
  border: 1px solid #efd7a4;
  border-left: 4px solid var(--routine, #c47b1a);
  border-radius: 12px;
  background: #fffaf0;
}

.routine-setting-card .field-row {
  grid-template-columns: minmax(0, 1fr) 120px;
  margin-top: 8px;
}

.routine-title {
  margin: 0;
  font-size: 15px;
}

.routine-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
  color: #8a5a12;
  font-size: 12px;
}

.routine-empty {
  padding: 8px 2px 2px;
  color: var(--muted);
  line-height: 1.7;
}

.routine-create-form {
  display: grid;
  gap: 12px;
  padding-bottom: 28px;
}

.routine-create-form .field-row {
  grid-template-columns: minmax(0, 1fr) 120px;
}

.form-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.routine-settings-panel > .panel-header {
  padding-right: 28px;
  padding-left: 28px;
}

.routine-settings-panel > :not(.panel-header) {
  padding-right: 28px;
  padding-left: 28px;
}

.routine-settings-panel .routine-guard-note,
.routine-settings-panel .routine-unlock-note {
  margin-right: 0;
  margin-left: 0;
}

@media (max-width: 980px) {
  .routine-settings-panel > .panel-header {
    padding-right: 20px;
    padding-left: 20px;
  }

  .routine-settings-panel > :not(.panel-header) {
    padding-right: 20px;
    padding-left: 20px;
  }
}
</style>
