import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as settingsApi from '../api/settings'
import type { Profile } from '../types/api'

export const useSettingsStore = defineStore('settings', () => {
  const profile = ref<Profile>({
    display_name: '',
    avatar_data: '',
    focus_minutes: 25,
    break_minutes: 5,
  })
  const loaded = ref(false)

  async function loadSettings() {
    const data = await settingsApi.fetchSettings()
    profile.value = data.profile
    loaded.value = true
    return data
  }

  async function saveProfile(patch: Partial<Profile>) {
    const updated = await settingsApi.updateProfile(patch)
    profile.value = { ...profile.value, ...updated }
    return updated
  }

  return { profile, loaded, loadSettings, saveProfile }
})
