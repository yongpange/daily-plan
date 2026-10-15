<script setup lang="ts">
// 图片条 + 添加/拖拽/粘贴 —— 平移 web-legacy app.js 的 imageThumbMarkup/renderImageStrip/
// bindImageInput/bindImageDrop/bindImagePaste/syncImageAdder
import { computed, ref } from 'vue'
import { imageUrl } from '../../api/images'
import type { MemoImage } from '../../types/api'
import type { PendingImage } from '../../stores/memo'
import { useUiStore } from '../../stores/ui'

const props = defineProps<{
  images?: MemoImage[]
  pending?: PendingImage[]
  removable?: boolean
}>()

const emit = defineEmits<{
  (e: 'add-files', files: File[]): void
  (e: 'remove-saved', imageId: number): void
  (e: 'remove-pending', localId: string): void
}>()

const ui = useUiStore()
const fileInput = ref<HTMLInputElement | null>(null)
const isDropping = ref(false)

const savedImages = computed(() => props.images ?? [])
const pendingImages = computed(() => props.pending ?? [])
const totalCount = computed(() => savedImages.value.length + pendingImages.value.length)
const addHidden = computed(() => totalCount.value >= 9)

function onInputChange() {
  const files = [...(fileInput.value?.files ?? [])]
  fileInput.value && (fileInput.value.value = '')
  if (files.length) emit('add-files', files)
}

function transferHasFile(dataTransfer: DataTransfer | null): boolean {
  if (!dataTransfer) return false
  if ([...dataTransfer.types].includes('Files')) return true
  return [...dataTransfer.items].some((item) => item.kind === 'file' || item.type.startsWith('image/'))
}

function onDragEnter(event: DragEvent) {
  if (!transferHasFile(event.dataTransfer)) return
  event.preventDefault()
  isDropping.value = true
}

function onDragOver(event: DragEvent) {
  if (!transferHasFile(event.dataTransfer)) return
  event.preventDefault()
  isDropping.value = true
}

function onDragLeave(event: DragEvent) {
  const target = event.currentTarget as HTMLElement
  if (event.relatedTarget && target.contains(event.relatedTarget as Node)) return
  isDropping.value = false
}

function onDrop(event: DragEvent) {
  if (!transferHasFile(event.dataTransfer)) return
  event.preventDefault()
  isDropping.value = false
  const files = [...(event.dataTransfer?.files ?? [])].filter((file) => file.type.startsWith('image/'))
  if (!files.length) {
    ui.notify('请拖入图片文件', true)
    return
  }
  emit('add-files', files)
}

function viewSaved(image: MemoImage) {
  ui.openImageViewer(savedImages.value, savedImages.value.findIndex((item) => item.id === image.id))
}

function viewPending(item: PendingImage) {
  // 用原图 data URL 在页内查看。window.open(data:) 会被浏览器拦成 about:blank。
  const sources = pendingImages.value.map((image) => image.prepared.original || image.preview)
  const index = pendingImages.value.findIndex((image) => image.localId === item.localId)
  ui.openLocalImages(sources, index)
}
</script>

<template>
  <div
    class="image-composer"
    :class="{ 'is-dropping': isDropping }"
    @dragenter="onDragEnter"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <div v-if="totalCount" class="image-strip">
      <span v-for="image in savedImages" :key="`saved-${image.id}`" class="image-tile">
        <button type="button" class="image-thumb" aria-label="查看原图" @click="viewSaved(image)">
          <img :src="imageUrl(image.id, true)" alt="图片缩略图" />
        </button>
        <button
          v-if="removable"
          type="button"
          class="image-remove"
          aria-label="移除图片"
          @click="emit('remove-saved', image.id)"
        >
          ×
        </button>
      </span>
      <span v-for="item in pendingImages" :key="item.localId" class="image-tile">
        <button type="button" class="image-thumb" aria-label="查看原图" @click="viewPending(item)">
          <img :src="item.preview" alt="待上传图片" />
        </button>
        <button type="button" class="image-remove" aria-label="移除图片" @click="emit('remove-pending', item.localId)">
          ×
        </button>
      </span>
    </div>
    <label v-if="!addHidden" class="image-add">
      <input ref="fileInput" type="file" accept="image/*" multiple @change="onInputChange" />
      添加图片
    </label>
  </div>
</template>

<style scoped>
.image-composer {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}

.image-composer.is-dropping {
  box-shadow: inset 0 0 0 2px #7dbe9b;
  border-radius: 10px;
}

.image-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.image-strip:empty {
  display: none;
}

.image-tile {
  position: relative;
  width: 72px;
  height: 72px;
}

.image-thumb {
  width: 72px;
  height: 72px;
  padding: 0;
  border: 1px solid rgba(23, 32, 29, 0.08);
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
  cursor: zoom-in;
  transition:
    transform 160ms ease,
    box-shadow 160ms ease;
}

.image-thumb:hover,
.image-thumb:focus-visible {
  transform: translateY(-1px);
  box-shadow: 0 8px 18px rgba(21, 35, 29, 0.16);
}

.image-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  z-index: 1;
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 50%;
  color: #fff;
  background: rgba(23, 32, 29, 0.72);
  font-size: 13px;
  line-height: 18px;
  cursor: pointer;
}

.image-tile.is-uploading {
  border-radius: 10px;
  background: linear-gradient(90deg, #e7eee9 25%, #f7faf8 37%, #e7eee9 63%);
  background-size: 400% 100%;
  animation: image-shimmer 1.1s ease infinite;
}

@keyframes image-shimmer {
  0% {
    background-position: 100% 0;
  }

  100% {
    background-position: 0 0;
  }
}

.image-add {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  width: fit-content;
  min-height: 30px;
  padding: 0 10px 0 8px;
  border: 1px dashed #b7c4bc;
  border-radius: 999px;
  color: var(--green);
  background: #fff;
  font-size: 12px;
  font-weight: 750;
  cursor: pointer;
}

.image-add::before {
  content: '+';
  font-size: 16px;
  line-height: 1;
}

.image-add:hover {
  border-color: #7dbe9b;
  background: var(--green-soft);
}

.image-add input {
  display: none;
}
</style>
