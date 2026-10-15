import http from './http'
import type { Profile, SettingsResponse } from '../types/api'

export function fetchSettings() {
  return http.get<SettingsResponse>('/settings').then((r) => r.data)
}

export function updateProfile(profile: Partial<Profile>) {
  return http.patch<Profile>('/settings', profile).then((r) => r.data)
}
