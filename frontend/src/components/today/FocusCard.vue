<script setup lang="ts">
// “今天最想推进的一件事” —— 平移 focusInput + scheduleDaySave（550ms 防抖在 store 内）
import { useDayStore } from '../../stores/day'

const dayStore = useDayStore()

function onInput() {
  dayStore.scheduleDaySave()
}
</script>

<template>
  <section class="focus-card">
    <label for="focusInput">今天最想推进的一件事</label>
    <input
      id="focusInput"
      v-model="dayStore.focusDraft"
      type="text"
      maxlength="500"
      placeholder="即使其他事情被打断，今天也要推进什么？"
      @input="onInput"
    />
    <span id="daySaveStatus" class="save-status" aria-live="polite">{{ dayStore.saveStatus }}</span>
  </section>
</template>

<style scoped>
.focus-card {
  gap: 10px;
  margin-bottom: 8px;
  padding: 4px 12px;
}

.focus-card input {
  height: 34px;
}
</style>
