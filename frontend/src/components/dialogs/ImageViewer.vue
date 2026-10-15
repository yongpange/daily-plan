<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { imageUrl } from '../../api/images'
import { useUiStore } from '../../stores/ui'

const ui = useUiStore()
const dialogRef = ref<HTMLDialogElement | null>(null)

watch(
  () => ui.viewerOpen,
  async (open) => {
    await nextTick()
    const dialog = dialogRef.value
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  },
)

const currentSrc = computed(() => {
  const item = ui.viewerItems[ui.viewerIndex]
  if (!item) return ''
  return item.kind === 'local' ? item.src : imageUrl(item.id)
})

function close() {
  ui.closeImageViewer()
}
</script>

<template>
  <dialog
    ref="dialogRef"
    class="image-viewer"
    @close="ui.closeImageViewer"
    @cancel="ui.closeImageViewer"
  >
    <button type="button" id="closeImageViewer" class="image-viewer-close" aria-label="关闭" @click="close">×</button>
    <button
      type="button"
      id="previousImage"
      class="image-viewer-nav prev"
      aria-label="上一张"
      @click="ui.stepImageViewer(-1)"
    >
      ‹
    </button>
    <div class="image-viewer-stage">
      <img
        v-if="currentSrc"
        id="imageViewerPicture"
        :key="currentSrc"
        :src="currentSrc"
        alt="原图"
      />
      <p v-if="ui.viewerItems.length > 1" id="imageViewerCaption">
        {{ ui.viewerIndex + 1 }} / {{ ui.viewerItems.length }}
      </p>
    </div>
    <button
      type="button"
      id="nextImage"
      class="image-viewer-nav next"
      aria-label="下一张"
      @click="ui.stepImageViewer(1)"
    >
      ›
    </button>
  </dialog>
</template>

<style scoped>
.image-viewer {
  width: auto;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 48px);
  padding: 0;
  border: 0;
  background: transparent;
}

.image-viewer:not([open]) {
  display: none;
}

.image-viewer::backdrop {
  background: rgba(15, 22, 19, 0.82);
}

.image-viewer-stage {
  display: grid;
  place-items: center;
}

.image-viewer-stage img {
  width: auto;
  height: auto;
  max-width: calc(100vw - 144px);
  max-height: calc(100vh - 120px);
  object-fit: contain;
  border-radius: 10px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.4);
}

.image-viewer-stage p {
  margin: 10px 0 0;
  color: rgba(255, 255, 255, 0.75);
  font-size: 12px;
  text-align: center;
}

.image-viewer-close {
  position: fixed;
  z-index: 5;
  top: 18px;
  right: 22px;
  width: 40px;
  height: 40px;
  border: 0;
  border-radius: 50%;
  color: #fff;
  background: rgba(255, 255, 255, 0.14);
  font-size: 22px;
}

.image-viewer-nav {
  position: fixed;
  z-index: 5;
  top: 50%;
  width: 44px;
  height: 44px;
  border: 0;
  border-radius: 50%;
  color: #fff;
  background: rgba(255, 255, 255, 0.14);
  font-size: 26px;
  transform: translateY(-50%);
}

.image-viewer-nav.prev {
  left: 22px;
}

.image-viewer-nav.next {
  right: 22px;
}
</style>
