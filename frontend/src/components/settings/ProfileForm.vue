<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { errorMessage } from '../../api/http'
import { useSettingsStore } from '../../stores/settings'
import { useUiStore } from '../../stores/ui'
import { resizeAvatar } from '../../utils/image'
import { STORAGE, safeStorageSet } from '../../utils/storage'

const settingsStore = useSettingsStore()
const ui = useUiStore()

const displayName = ref('')
const focusMinutes = ref(25)
const breakMinutes = ref(5)
/** undefined = 沿用 store 里的头像；null = 已移除；string = 新选择的头像 */
const avatarData = ref<string | null | undefined>(undefined)
const saving = ref(false)

// 平移 renderProfile 填表副作用
watch(
  () => settingsStore.loaded,
  (loaded) => {
    if (!loaded) return
    displayName.value = settingsStore.profile.display_name.trim()
    focusMinutes.value = settingsStore.profile.focus_minutes || 25
    breakMinutes.value = settingsStore.profile.break_minutes || 5
  },
  { immediate: true },
)

const initial = computed(() => (displayName.value || '设').slice(0, 1))
const previewAvatar = computed(() => avatarData.value ?? settingsStore.profile.avatar_data)

async function onAvatarChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    avatarData.value = await resizeAvatar(file)
  } catch (error) {
    ui.notify(errorMessage(error, '这张图片无法读取'), true)
  } finally {
    input.value = ''
  }
}

function onRemoveAvatar() {
  avatarData.value = null
}

// 平移 saveProfile
async function onSubmit() {
  saving.value = true
  try {
    await settingsStore.saveProfile({
      display_name: displayName.value,
      avatar_data: avatarData.value === undefined ? settingsStore.profile.avatar_data : avatarData.value,
      focus_minutes: Number(focusMinutes.value) || 25,
      break_minutes: Number(breakMinutes.value) || 5,
    })
    avatarData.value = undefined
    // renderProfile 的 localStorage 兜底副作用（timer store 会读）
    safeStorageSet(STORAGE.focusMinutes, settingsStore.profile.focus_minutes || 25)
    safeStorageSet(STORAGE.breakMinutes, settingsStore.profile.break_minutes || 5)
    ui.notify('资料已保存')
  } catch (error) {
    ui.notify(errorMessage(error), true)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form id="profileForm" class="settings-form" @submit.prevent="onSubmit">
    <div class="avatar-editor">
      <span id="avatarPreview" class="avatar-preview">
        <img v-if="typeof previewAvatar === 'string' && previewAvatar.startsWith('data:image/')" alt="" :src="previewAvatar" />
        <template v-else>{{ initial }}</template>
      </span>
      <div>
        <label class="button subtle compact avatar-upload">
          上传头像
          <input id="avatarInput" type="file" accept="image/*" hidden @change="onAvatarChange" />
        </label>
        <button id="removeAvatar" class="button subtle compact" type="button" @click="onRemoveAvatar">
          移除
        </button>
        <p>头像只会保存在本机数据库里。</p>
      </div>
    </div>
    <label>
      <span>显示名称</span>
      <input id="displayNameInput" v-model="displayName" type="text" maxlength="40" placeholder="例如：勇攀" />
    </label>
    <div class="field-row">
      <label>
        <span>默认专注分钟</span>
        <input id="settingFocusMinutes" v-model.number="focusMinutes" type="number" min="5" max="180" value="25" />
      </label>
      <label>
        <span>默认休息分钟</span>
        <input id="settingBreakMinutes" v-model.number="breakMinutes" type="number" min="1" max="60" value="5" />
      </label>
    </div>
    <div class="form-actions">
      <button type="submit" class="button primary" :disabled="saving">
        {{ saving ? '保存中…' : '保存资料' }}
      </button>
    </div>
  </form>
</template>

<style scoped>
.settings-form {
  display: grid;
  gap: 12px;
  padding-right: 28px;
  padding-bottom: 28px;
  padding-left: 28px;
}

.settings-form .field-row {
  grid-template-columns: 1fr 1fr;
}

.avatar-editor {
  display: flex;
  align-items: center;
  gap: 14px;
}

.avatar-preview {
  display: grid;
  place-items: center;
  overflow: hidden;
  width: 72px;
  height: 72px;
  flex: 0 0 72px;
  border-radius: 50%;
  color: #8a5a12;
  background: #fff4d9;
  font-size: 24px;
  font-weight: 800;
}

.avatar-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-editor p {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 12px;
}

.avatar-upload input {
  display: none;
}

.form-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 980px) {
  .settings-form {
    padding-right: 20px;
    padding-left: 20px;
  }
}
</style>
