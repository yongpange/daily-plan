<script setup lang="ts">
// 已保存感悟的缩略图条。点开走页内查看器，和记一条、感悟卡片同一套尺寸。
import type { MemoImage } from '../../types/api'
import { imageUrl } from '../../api/images'
import { useUiStore } from '../../stores/ui'

const props = defineProps<{ images?: MemoImage[] | null }>()

const ui = useUiStore()

function view(index: number) {
  if (!props.images?.length) return
  ui.openImageViewer(props.images, index)
}
</script>

<template>
  <div v-if="images?.length" class="image-strip">
    <span v-for="(image, index) in images" :key="image.id" class="image-tile">
      <button type="button" class="image-thumb" aria-label="查看原图" @click.stop="view(index)">
        <img :src="imageUrl(image.id, true)" alt="图片缩略图" />
      </button>
    </span>
  </div>
</template>

<style scoped>
.image-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
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
}

.image-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>
