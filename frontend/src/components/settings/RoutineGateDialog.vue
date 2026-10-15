<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useRoutineStore } from '../../stores/routine'
import BaseDialog from '../common/BaseDialog.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const routineStore = useRoutineStore()

const answers = ref<string[]>([])
const submitting = ref(false)
const questionsRef = ref<HTMLElement | null>(null)

// 平移 openRoutineGate 的题目渲染；换题（答错后）时清空答案并聚焦第一题
watch(
  () => routineStore.challenge,
  async (challenge) => {
    answers.value = challenge ? challenge.questions.map(() => '') : []
    if (!challenge) return
    await nextTick()
    questionsRef.value?.querySelector('input')?.focus()
  },
)

async function onSubmit() {
  if (!routineStore.challenge) return
  submitting.value = true
  try {
    const passed = await routineStore.submitRoutineGate(answers.value.map((value) => Number(value) || 0))
    if (passed) emit('close')
  } finally {
    submitting.value = false
  }
}

function onClose() {
  emit('close')
}
</script>

<template>
  <BaseDialog :open="props.open" @close="onClose">
    <form method="dialog" @submit.prevent="onSubmit">
      <div class="dialog-header">
        <div>
          <p class="eyebrow">防止一时冲动</p>
          <h2>先答对 3 道题</h2>
          <p>每道题都包含加减乘除。3 道全部答对后，才能修改每日必做。</p>
        </div>
        <button class="dialog-close" type="button" aria-label="关闭" @click="onClose">×</button>
      </div>
      <div v-if="routineStore.challenge" id="routineQuestions" ref="questionsRef" class="routine-questions">
        <label v-for="(question, index) in routineStore.challenge.questions" :key="index">
          <span>第 {{ index + 1 }} 题：{{ question.prompt }} = ？</span>
          <input v-model="answers[index]" type="number" inputmode="numeric" required />
        </label>
      </div>
      <div class="dialog-actions">
        <button class="button subtle" type="button" @click="onClose">取消</button>
        <button type="submit" class="button primary" :disabled="submitting">
          {{ submitting ? '核对中…' : '提交答案' }}
        </button>
      </div>
    </form>
  </BaseDialog>
</template>

<style scoped>
.routine-questions {
  display: grid;
  gap: 12px;
}

.routine-questions label {
  display: grid;
  align-content: start;
  gap: 6px;
}

.routine-questions label > span {
  color: #59645f;
  font-size: 11px;
  font-weight: 750;
  font-variant-numeric: tabular-nums;
}
</style>
