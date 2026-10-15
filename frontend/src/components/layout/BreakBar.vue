<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useTimerStore } from '../../stores/timer'
import { formatClock } from '../../utils/format'

const timerStore = useTimerStore()

const visible = computed(() => timerStore.isBreakActive)
const breakTime = computed(() => formatClock(timerStore.breakRemaining / 1000))

function syncStickyOffset() {
  const runningBar = document.getElementById('runningBar')
  const runningHeight = runningBar && !runningBar.hidden ? runningBar.offsetHeight : 0
  const breakHeight = visible.value ? document.getElementById('breakBar')?.offsetHeight ?? 0 : 0
  document.documentElement.style.setProperty('--bar-height', `${runningHeight + breakHeight}px`)
}

watch(visible, () => {
  requestAnimationFrame(syncStickyOffset)
})

onMounted(() => {
  requestAnimationFrame(syncStickyOffset)
})
</script>

<template>
  <div v-show="visible" id="breakBar" class="break-bar">
    <div>
      <span aria-hidden="true">☕</span>
      <strong>休息一下</strong>
      <time>{{ breakTime }}</time>
    </div>
    <button type="button" class="button subtle compact" @click="timerStore.stopBreak">结束休息</button>
  </div>
</template>
