<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useTimerStore } from '../../stores/timer'

const timerStore = useTimerStore()

const visible = computed(() => timerStore.isRunning)

/** 平移 syncStickyOffset：顶条显隐时把高度写进 --bar-height / --running-height */
function syncStickyOffset() {
  const runningHeight = visible.value ? document.getElementById('runningBar')?.offsetHeight ?? 0 : 0
  document.documentElement.style.setProperty('--running-height', `${runningHeight}px`)
  const breakBar = document.getElementById('breakBar')
  const breakHeight = breakBar && !breakBar.hidden ? breakBar.offsetHeight : 0
  document.documentElement.style.setProperty('--bar-height', `${runningHeight + breakHeight}px`)
}

async function onStop() {
  await timerStore.stopTimer({ entryId: timerStore.activeTimer?.entry_id ?? null })
}

watch(visible, () => {
  requestAnimationFrame(syncStickyOffset)
})

onMounted(() => {
  requestAnimationFrame(syncStickyOffset)
})
</script>

<template>
  <div v-show="visible" id="runningBar" class="running-bar">
    <div>
      <span class="pulse-dot" aria-hidden="true"></span>
      <span class="running-label">{{ timerStore.runningIsFocus ? '专注倒计时' : '正在计时' }}</span>
      <strong>{{ timerStore.activeTimer?.title }}</strong>
      <time>{{ timerStore.runningDisplayTime }}</time>
    </div>
    <div>
      <span v-show="timerStore.runningIsFocus" class="running-progress">
        <i :style="{ width: `${timerStore.runningProgressPercent}%` }"></i>
      </span>
      <button type="button" class="button danger compact" @click="onStop">停止</button>
    </div>
  </div>
</template>
