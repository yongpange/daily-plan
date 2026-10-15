import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import * as routinesApi from '../api/routines'
import type { PublicRoutine, RoutineChallenge } from '../types/api'
import { useUiStore } from './ui'
import { useTimerStore } from './timer'
import router from '../router'

export const useRoutineStore = defineStore('routine', () => {
  const ui = useUiStore()

  /** 设置页管理的必做列表（来自 /api/settings） */
  const routines = ref<PublicRoutine[]>([])
  const unlockToken = ref('')
  const unlockExpiresAt = ref('')
  const challenge = ref<RoutineChallenge | null>(null)

  /** 解锁状态（平移旧实现 token 只在内存 + 10 分钟有效） */
  const isUnlocked = computed(
    () => Boolean(unlockToken.value) && (!unlockExpiresAt.value || new Date(unlockExpiresAt.value).getTime() > Date.now()),
  )

  /** 重新锁定（到期或手动调用） */
  function lock() {
    unlockToken.value = ''
    unlockExpiresAt.value = ''
  }

  function setRoutines(list: PublicRoutine[]) {
    routines.value = list
  }

  async function toggleRoutine(routineId: number, date: string, completed: boolean) {
    const { useDayStore } = await import('./day')
    const result = await routinesApi.checkRoutine(routineId, date, completed)
    const dayStore = useDayStore()
    if (dayStore.day) dayStore.day.routines = result.routines
    return result
  }

  async function startRoutineTimer(routineId: number, date: string) {
    const { useDayStore } = await import('./day')
    await routinesApi.startRoutineTimer(routineId, date)
    await useDayStore().loadDay()
  }

  async function stopRoutineTimer(routineId: number) {
    const result = await routinesApi.stopRoutineTimer(routineId)
    const { useDayStore } = await import('./day')
    if (router.currentRoute.value.name === 'today') {
      await useDayStore().loadDay()
    } else {
      await useTimerStore().refreshGlobalTimer()
    }
    return result
  }

  async function createRoutine(payload: { title: string; note?: string; estimate_minutes?: number }) {
    const created = await routinesApi.createRoutine(payload)
    routines.value.push(created)
    return created
  }

  async function saveRoutineCard(
    routineId: number,
    payload: { title?: string; note?: string; estimate_minutes?: number },
  ) {
    const updated = await routinesApi.updateRoutine(routineId, { ...payload, unlock_token: unlockToken.value })
    const index = routines.value.findIndex((routine) => routine.id === routineId)
    if (index >= 0) routines.value[index] = updated
    return updated
  }

  async function deleteRoutineCard(routineId: number) {
    await routinesApi.deleteRoutine(routineId, unlockToken.value)
    routines.value = routines.value.filter((routine) => routine.id !== routineId)
  }

  async function openRoutineGate() {
    challenge.value = await routinesApi.createChallenge()
  }

  async function submitRoutineGate(answers: number[]) {
    if (!challenge.value) return false
    try {
      const result = await routinesApi.verifyChallenge(challenge.value.id, answers)
      unlockToken.value = result.unlock_token
      unlockExpiresAt.value = result.expires_at
      challenge.value = null
      ui.notify('验证通过，可以修改每日必做')
      return true
    } catch (error) {
      ui.notify(error instanceof Error ? error.message : '验证没有通过', true)
      challenge.value = await routinesApi.createChallenge()
      return false
    }
  }

  return {
    routines,
    unlockToken,
    unlockExpiresAt,
    isUnlocked,
    lock,
    challenge,
    setRoutines,
    toggleRoutine,
    startRoutineTimer,
    stopRoutineTimer,
    createRoutine,
    saveRoutineCard,
    deleteRoutineCard,
    openRoutineGate,
    submitRoutineGate,
  }
})
