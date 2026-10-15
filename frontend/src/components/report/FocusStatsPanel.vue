<script setup lang="ts">
import { computed } from 'vue'
import { useReportStore } from '../../stores/report'
import { formatHours } from '../../utils/format'

const reportStore = useReportStore()

const focus = computed(() => reportStore.report?.focus)
</script>

<template>
  <section class="panel focus-stats-panel">
    <div class="panel-header compact-header">
      <div>
        <p class="eyebrow">专注统计</p>
        <h2>专注段</h2>
      </div>
    </div>
    <div class="focus-stats">
      <div class="focus-stat">
        <strong>{{ focus?.completed_count || 0 }}</strong>
        <span>完整专注段</span>
      </div>
      <div class="focus-stat">
        <strong>{{ focus?.segment_count || 0 }}</strong>
        <span>全部专注段</span>
      </div>
      <div class="focus-stat">
        <strong>{{ formatHours(Number(focus?.actual_seconds || 0) / 60) }}</strong>
        <span>专注有效时间</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.focus-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding: 3px 20px 20px;
}

.focus-stat {
  padding: 13px 8px;
  border-radius: 10px;
  background: #f7f5fb;
  text-align: center;
}

.focus-stat strong,
.focus-stat span {
  display: block;
}

.focus-stat strong {
  color: var(--purple);
  font-size: 19px;
}

.focus-stat span {
  margin-top: 4px;
  color: var(--muted);
  font-size: 10px;
}
</style>
