<script setup lang="ts">
// 收工入口卡片 —— 平移 index.html shutdown-panel + renderDay 的按钮/提示切换
import { useDayStore } from '../../stores/day'

const emit = defineEmits<{ (e: 'open-close'): void }>()

const dayStore = useDayStore()
</script>

<template>
  <section class="panel shutdown-panel">
    <span class="shutdown-icon">↘</span>
    <h2>今天收工前</h2>
    <p>处理每一条未完成任务：完成、明天继续、改期或放弃，并留下原因。</p>
    <button id="openCloseDay" class="button dark full-width" @click="emit('open-close')">
      {{ dayStore.isClosed ? '重新查看并收工' : '开始收工复盘' }}
    </button>
    <p v-if="dayStore.isClosed" id="closedDayNote" class="closed-note">
      这一天已经完成收工复盘
    </p>
  </section>
</template>

<style scoped>
.shutdown-panel {
  overflow: hidden;
  padding: 20px;
  color: #fff;
  background:
    radial-gradient(circle at 100% 0, rgba(86, 149, 116, 0.35), transparent 12rem),
    var(--ink);
}

.shutdown-panel h2 {
  margin-bottom: 7px;
}

.shutdown-panel p {
  color: #c0c9c5;
  line-height: 1.6;
}

.shutdown-icon {
  display: grid;
  width: 35px;
  height: 35px;
  margin-bottom: 18px;
  place-items: center;
  border-radius: 10px;
  color: #bfe4cf;
  background: rgba(255, 255, 255, 0.08);
  font-size: 18px;
}

.shutdown-panel .button {
  color: var(--ink);
  background: #fff;
}

.closed-note {
  margin: 11px 0 0 !important;
  color: #9fd6b8 !important;
  text-align: center;
  font-size: 11px;
}
</style>
