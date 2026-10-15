<script setup lang="ts">
// 当天概览四张卡片 —— 平移 renderSummary 的摘要输出（数据来自 dayStore.summary）
import { useDayStore } from '../../stores/day'

const dayStore = useDayStore()
</script>

<template>
  <section class="summary-grid" aria-label="当天概览">
    <article class="summary-card accent">
      <span>计划投入</span>
      <strong>{{ dayStore.summary.plannedLabel }}</strong>
      <small></small>
    </article>
    <article class="summary-card">
      <span>实际有效</span>
      <strong>{{ dayStore.summary.actualLabel }}</strong>
      <small>由计时器自动累计</small>
    </article>
    <article class="summary-card">
      <span>完成进度</span>
      <strong>{{ dayStore.summary.completedLabel }}</strong>
      <div class="progress-track">
        <span :style="{ width: `${dayStore.summary.completionPercent}%` }"></span>
      </div>
    </article>
    <article class="summary-card">
      <span>预估偏差</span>
      <strong>{{ dayStore.summary.varianceLabel }}</strong>
      <small>{{ dayStore.summary.varianceHint || '完成计时后可对照' }}</small>
    </article>
  </section>
</template>

<style scoped>
.summary-grid {
  gap: 8px;
  margin-bottom: 8px;
}

.summary-card {
  padding: 8px 12px;
}

.summary-card > span {
  margin-bottom: 2px;
}

.summary-card > strong {
  margin-bottom: 1px;
  font-size: 18px;
}

.progress-track {
  margin-top: 6px;
}
</style>
