import { defineStore } from 'pinia'
import { ref } from 'vue'
import { onPendingChange } from '../api/http'
import type { MemoImage } from '../types/api'

export type ViewerItem = { kind: 'saved'; id: number } | { kind: 'local'; src: string }

let toastTimer: number | undefined

export const useUiStore = defineStore('ui', () => {
  // toast
  const toastMessage = ref('')
  const toastIsError = ref(false)
  const toastVisible = ref(false)

  function notify(message: string, isError = false) {
    toastMessage.value = message
    toastIsError.value = isError
    toastVisible.value = true
    window.clearTimeout(toastTimer)
    toastTimer = window.setTimeout(() => {
      toastVisible.value = false
    }, isError ? 5000 : 2800)
  }

  // 全局 loading（来自 axios 拦截器的在飞请求计数）
  const pendingCount = ref(0)
  const globalLoading = ref(false)
  onPendingChange((count) => {
    pendingCount.value = count
    globalLoading.value = count > 0
  })

  // 图片查看器（已保存图片走 id，待上传图片走本地 data URL，避免 window.open 被拦成 about:blank）
  const viewerItems = ref<ViewerItem[]>([])
  const viewerIndex = ref(0)
  const viewerOpen = ref(false)

  function openItems(items: ViewerItem[], index: number) {
    if (!items.length || index < 0 || index >= items.length) return
    viewerItems.value = items
    viewerIndex.value = index
    viewerOpen.value = true
  }

  function openImageViewer(images: MemoImage[], index: number) {
    openItems(
      images.map((image) => ({ kind: 'saved', id: image.id })),
      index,
    )
  }

  function openLocalImages(sources: string[], index: number) {
    openItems(
      sources.map((src) => ({ kind: 'local', src })),
      index,
    )
  }

  function stepImageViewer(direction: number) {
    const total = viewerItems.value.length
    if (!total) return
    viewerIndex.value = (viewerIndex.value + direction + total) % total
  }

  function closeImageViewer() {
    viewerOpen.value = false
  }

  return {
    toastMessage,
    toastIsError,
    toastVisible,
    notify,
    pendingCount,
    globalLoading,
    viewerItems,
    viewerIndex,
    viewerOpen,
    openImageViewer,
    openLocalImages,
    stepImageViewer,
    closeImageViewer,
  }
})

/** 提示音（平移 playTone：AudioContext 660Hz） */
export function playTone() {
  try {
    const AudioContextCtor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AudioContextCtor) return
    const context = new AudioContextCtor()
    const oscillator = context.createOscillator()
    const gain = context.createGain()
    oscillator.type = 'sine'
    oscillator.frequency.value = 660
    gain.gain.setValueAtTime(0.08, context.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.5)
    oscillator.connect(gain)
    gain.connect(context.destination)
    oscillator.start()
    oscillator.stop(context.currentTime + 0.5)
  } catch {
    // 音频提示失败不影响主流程
  }
}
