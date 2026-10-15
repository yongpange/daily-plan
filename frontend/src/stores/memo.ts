import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as memoApi from '../api/memos'
import * as imageApi from '../api/images'
import type { Memo, MemoSource, MemoTemplate } from '../types/api'
import { prepareImage, type PreparedImage } from '../utils/image'
import { useUiStore } from './ui'

export interface PendingImage {
  localId: string
  preview: string
  prepared: PreparedImage
}

let searchTimer: number | undefined
const readLocks = new Set<string>()

export const useMemoStore = defineStore('memo', () => {
  const ui = useUiStore()

  const memos = ref<Memo[]>([])
  const todayMemos = ref<Memo[]>([])
  const memoSources = ref<MemoSource[]>([])
  const suggestedTags = ref<string[]>([])
  const templates = ref<MemoTemplate[]>([])
  /** 感悟库当前来源过滤（null = 全部） */
  const memoSource = ref<{ kind: string; id: number } | null>(null)

  // 待上传图片桶（quick=今日随手记，compose=感悟库）
  const pendingQuickImages = ref<PendingImage[]>([])
  const pendingComposeImages = ref<PendingImage[]>([])
  // 上传失败后的草稿（再次提交走 PATCH 重试）
  const quickMemoDraftId = ref<number | null>(null)
  const composeMemoDraftId = ref<number | null>(null)

  async function loadMemos(query = '') {
    const [memosData, sourcesData] = await Promise.all([
      memoApi.fetchMemos({
        query,
        limit: 200,
        source_kind: (memoSource.value?.kind as 'routine' | 'thread' | undefined) ?? undefined,
        source_id: memoSource.value?.id,
      }),
      memoApi.fetchMemoSources(),
    ])
    memos.value = memosData
    memoSources.value = sourcesData
  }

  /** 搜索防抖 300ms（平移 memoSearchTimer） */
  function searchMemosDebounced(query: string, callback: () => Promise<void>) {
    window.clearTimeout(searchTimer)
    searchTimer = window.setTimeout(() => {
      void callback()
    }, 300)
  }

  async function loadSuggestedTags() {
    const data = await memoApi.fetchSuggestedTags()
    suggestedTags.value = data.tags
  }

  async function loadTemplates() {
    templates.value = await memoApi.fetchMemoTemplates()
  }

  async function saveTemplate(payload: { id?: number; name: string; content: string }) {
    await memoApi.saveMemoTemplate(payload)
    await loadTemplates()
  }

  async function deleteTemplate(templateId: number) {
    await memoApi.deleteMemoTemplate(templateId)
    await loadTemplates()
  }

  // ---------- 图片 ----------

  async function addFilesToBucket(files: File[], bucket: 'quick' | 'compose') {
    const list = bucket === 'quick' ? pendingQuickImages : pendingComposeImages
    for (const file of files) {
      if (list.value.length >= 9) {
        ui.notify('一条记录最多 9 张图片', true)
        break
      }
      try {
        const prepared = await prepareImage(file)
        list.value.push({
          localId: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
          preview: prepared.thumbnail,
          prepared,
        })
      } catch (error) {
        ui.notify(error instanceof Error ? error.message : '图片处理失败', true)
      }
    }
  }

  function removePendingImage(bucket: 'quick' | 'compose', localId: string) {
    const list = bucket === 'quick' ? pendingQuickImages : pendingComposeImages
    list.value = list.value.filter((item) => item.localId !== localId)
  }

  /** 上传桶内图片；失败时把剩余塞回桶并抛错（平移 uploadPendingImages） */
  async function uploadPendingImages(bucket: 'quick' | 'compose', ownerKey: number) {
    const list = bucket === 'quick' ? pendingQuickImages : pendingComposeImages
    const queue = [...list.value]
    list.value = []
    for (let index = 0; index < queue.length; index += 1) {
      try {
        await imageApi.uploadImage({
          owner_type: 'memo',
          owner_key: String(ownerKey),
          ...queue[index].prepared,
        })
      } catch (error) {
        list.value = queue.slice(index)
        throw error
      }
    }
  }

  /** 删除图片后同步剔除四处引用（平移 deleteSavedImage） */
  async function deleteSavedImage(imageId: number) {
    await imageApi.deleteImage(imageId)
    const strip = (images: Memo['images']) => (images || []).filter((image) => image.id !== imageId)
    if (pendingQuickImages.value.length === 0 && pendingComposeImages.value.length === 0) {
      // no-op，保持逻辑清晰
    }
    todayMemos.value.forEach((memo) => (memo.images = strip(memo.images)))
    memos.value.forEach((memo) => (memo.images = strip(memo.images)))
    ui.notify('图片已移除')
  }

  // ---------- 提交（POST + 图片上传 + 失败 PATCH 重试） ----------

  interface SubmitOptions {
    bucket: 'quick' | 'compose'
    date: string
    content: string
    tags: string
  }

  async function submitMemo(options: SubmitOptions) {
    const list = options.bucket === 'quick' ? pendingQuickImages : pendingComposeImages
    const draftRef = options.bucket === 'quick' ? quickMemoDraftId : composeMemoDraftId
    if (!options.content && !list.value.length && !draftRef.value) {
      ui.notify('先写下一句，或添加一张图片', true)
      return false
    }
    let memoId = draftRef.value
    const retrying = Boolean(memoId)
    if (!memoId) {
      try {
        const memo = await memoApi.createMemo({
          date: options.date,
          content: options.content,
          content_format: 'rich',
          tags: options.tags,
          has_images: list.value.length > 0,
        })
        memoId = Number(memo.id)
        draftRef.value = memoId
      } catch (error) {
        ui.notify(error instanceof Error ? error.message : '保存失败', true)
        return false
      }
    }
    try {
      await uploadPendingImages(options.bucket, memoId)
      if (retrying) {
        await memoApi.updateMemo(memoId, {
          date: options.date,
          content: options.content,
          content_format: 'rich',
          tags: options.tags,
        })
      }
    } catch {
      ui.notify('文字已经保存，剩下的图片可以再点一次保存', true)
      return false
    }
    draftRef.value = null
    list.value = []
    if (options.bucket === 'quick') {
      todayMemos.value = await memoApi.fetchMemos({ date: options.date, limit: 30 })
    } else {
      await loadMemos()
    }
    await loadSuggestedTags()
    return true
  }

  // ---------- 编辑 / 点阅 / 置顶 / 删除 ----------

  async function saveMemoEdit(
    memoId: number,
    payload: { date: string; content: string; tags: string; pinned: boolean },
  ) {
    await memoApi.updateMemo(memoId, { ...payload, content_format: 'rich' })
  }

  async function toggleMemoPin(memo: Memo) {
    const updated = await memoApi.updateMemo(Number(memo.id), { pinned: !memo.pinned })
    const replace = (list: Memo[]) => {
      const index = list.findIndex((item) => item.id === memo.id)
      if (index >= 0) list[index] = { ...list[index], pinned: updated.pinned }
    }
    replace(memos.value)
    replace(todayMemos.value)
  }

  async function deleteMemo(memoId: number) {
    await memoApi.deleteMemo(memoId)
    memos.value = memos.value.filter((memo) => memo.id !== memoId)
    todayMemos.value = todayMemos.value.filter((memo) => memo.id !== memoId)
  }

  /** 感悟 → 今日任务（平移 promoteMemo：先查重再创建） */
  async function promoteMemo(memo: Memo, date: string): Promise<boolean> {
    const { useDayStore } = await import('./day')
    const dayStore = useDayStore()
    const title = memo.content ? memo.content.replace(/\s+/g, ' ').trim().slice(0, 80) : ''
    if (!title) return false
    const exists = dayStore.entries.some((entry) => entry.title === title)
    if (exists) {
      ui.notify('今天的任务里已经有这条了', true)
      return false
    }
    await dayStore.createTask({ title, estimate_minutes: 30 })
    ui.notify('已加入今天的任务')
    return true
  }

  /** 点阅（防重锁 900ms，平移 memoReadLocks） */
  async function markMemoRead(kind: 'memo' | 'daily', id: number | string): Promise<boolean> {
    const lockKey = `${kind}:${id}`
    if (readLocks.has(lockKey)) return false
    readLocks.add(lockKey)
    window.setTimeout(() => readLocks.delete(lockKey), 900)
    const result = await memoApi.markMemoRead(kind, id)
    const patch = (list: Memo[]) => {
      const target = list.find((memo) => memo.id === id)
      if (target) {
        target.read_count = result.read_count
        target.last_read_at = result.last_read_at
        target.read_today = result.read_today
      }
    }
    patch(memos.value)
    patch(todayMemos.value)
    return result.counted
  }

  function openMemoSource(kind: string, id: number) {
    memoSource.value = { kind, id: Number(id) }
  }

  function clearMemoSource() {
    memoSource.value = null
  }

  return {
    memos,
    todayMemos,
    memoSources,
    suggestedTags,
    templates,
    memoSource,
    pendingQuickImages,
    pendingComposeImages,
    quickMemoDraftId,
    composeMemoDraftId,
    loadMemos,
    searchMemosDebounced,
    loadSuggestedTags,
    loadTemplates,
    saveTemplate,
    deleteTemplate,
    addFilesToBucket,
    removePendingImage,
    uploadPendingImages,
    deleteSavedImage,
    submitMemo,
    saveMemoEdit,
    toggleMemoPin,
    deleteMemo,
    promoteMemo,
    markMemoRead,
    openMemoSource,
    clearMemoSource,
  }
})
