<script setup lang="ts">
import { computed } from 'vue'
import { useReportStore } from '../../stores/report'
import { formatMinutes } from '../../utils/format'

const reportStore = useReportStore()

const projects = computed(() => reportStore.report?.projects ?? [])
</script>

<template>
  <section class="panel">
    <div class="panel-header compact-header">
      <div>
        <p class="eyebrow">时间去向</p>
        <h2>项目投入</h2>
      </div>
    </div>
    <div class="project-stats">
      <div v-if="!projects.length" class="empty-inline">开始计时后，这里会显示时间投入去向</div>
      <div v-for="(project, index) in projects" :key="index" class="project-row">
        <strong>{{ project.project_name }}</strong>
        <span class="project-actual">{{ formatMinutes(Number(project.actual_seconds) / 60) }}</span>
        <span>计划 {{ formatMinutes(project.estimate_minutes) }} · 完成 {{ project.completed_count }}/{{ project.total_count }}</span>
        <span>实际有效</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.project-stats {
  padding: 4px 20px 20px;
}

.project-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px 14px;
  padding: 13px 0;
  border-bottom: 1px solid var(--line);
}

.project-row:last-child {
  border-bottom: 0;
}

.project-row strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-row span {
  color: var(--muted);
  font-size: 11px;
}

.project-row .project-actual {
  color: var(--green);
  font-weight: 800;
}

.empty-inline {
  padding: 26px 8px;
  color: var(--muted);
  text-align: center;
  font-size: 12px;
}
</style>
