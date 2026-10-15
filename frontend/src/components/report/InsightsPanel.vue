<script setup lang="ts">
import { computed } from 'vue'
import { useReportStore } from '../../stores/report'

const reportStore = useReportStore()

const insights = computed(() => reportStore.report?.insights ?? [])
</script>

<template>
  <section class="panel insights-panel">
    <div class="panel-header compact-header">
      <div>
        <p class="eyebrow">把数据变成行动</p>
        <h2>复盘洞察</h2>
      </div>
    </div>
    <div class="insight-list">
      <article
        v-for="(item, index) in insights"
        :key="index"
        class="insight-item"
        :data-tone="item.tone"
      >
        <strong>{{ item.title }}</strong>
        <p>{{ item.body }}</p>
      </article>
    </div>
  </section>
</template>

<style scoped>
.insights-panel {
  grid-column: 1 / -1;
}

.insight-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 3px 20px 20px;
}

.insight-item {
  min-height: 112px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: #fafcfb;
}

.insight-item::before {
  display: block;
  width: 25px;
  height: 4px;
  margin-bottom: 12px;
  border-radius: 99px;
  background: #a9b8b1;
  content: "";
}

.insight-item[data-tone="warning"]::before {
  background: var(--yellow);
}

.insight-item[data-tone="positive"]::before {
  background: #61a981;
}

.insight-item[data-tone="info"]::before {
  background: #8e83bf;
}

.insight-item strong {
  display: block;
  margin-bottom: 6px;
}

.insight-item p {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.65;
}
</style>
