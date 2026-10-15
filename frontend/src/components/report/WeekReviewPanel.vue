<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useReportStore } from '../../stores/report'

const reportStore = useReportStore()

const draft = ref('')
watch(
  () => reportStore.report,
  (report) => {
    draft.value = report?.review || ''
  },
  { immediate: true },
)

const periodName = computed(
  () => ({ week: '本周', month: '本月', quarter: '本季度' })[reportStore.period],
)

const placeholder = computed(
  () =>
    ({
      week: '哪类任务总是低估？下周减少什么、继续什么、调整什么？',
      month: '这个月有哪些反复出现的规律？下个月停止什么、延续什么？',
      quarter: '这个季度的时间投向是否正确？下季度最重要的调整是什么？',
    })[reportStore.period],
)

async function save() {
  await reportStore.saveReview(draft.value)
}
</script>

<template>
  <section class="panel week-review-panel">
    <div class="panel-header compact-header">
      <div>
        <p class="eyebrow">形成下一步</p>
        <h2>{{ periodName }}结论</h2>
      </div>
      <span class="save-status">{{ reportStore.reviewStatus }}</span>
    </div>
    <textarea
      v-model="draft"
      rows="5"
      maxlength="10000"
      :placeholder="placeholder"
    ></textarea>
    <div class="form-actions">
      <button type="button" class="button primary" @click="save">保存复盘结论</button>
    </div>
  </section>
</template>

<style scoped>
.week-review-panel {
  grid-column: 1 / -1;
  padding-bottom: 20px;
}

.week-review-panel textarea {
  width: calc(100% - 40px);
  margin: 0 20px 13px;
  background: #fafcfb;
}

.week-review-panel .form-actions {
  margin: 0 20px;
}

.form-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}
</style>
