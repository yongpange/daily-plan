<script setup lang="ts">
// 心情选择（平移 mood-picker：5 档）
import { computed } from 'vue'

const props = defineProps<{ modelValue: number | null }>()
const emit = defineEmits<{ (e: 'select', value: number): void }>()

const options = [
  { value: 1, label: '很糟' },
  { value: 2, label: '有点糟' },
  { value: 3, label: '一般' },
  { value: 4, label: '不错' },
  { value: 5, label: '很好' },
]

const active = computed(() => props.modelValue)
</script>

<template>
  <fieldset class="mood-picker">
    <legend>今天感觉怎么样</legend>
    <div>
      <button
        v-for="option in options"
        :key="option.value"
        type="button"
        :data-mood="option.value"
        :class="{ 'is-active': active === option.value }"
        @click="emit('select', option.value)"
      >
        {{ option.label }}
      </button>
    </div>
  </fieldset>
</template>

<style scoped>
.mood-picker {
  margin: 0;
  padding: 0;
  border: 0;
}

.mood-picker legend {
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 650;
}

.mood-picker > div {
  display: flex;
  gap: 6px;
}

.mood-picker button {
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: #4e5a55;
  background: #fff;
  font-size: 12px;
  font-weight: 700;
}

.mood-picker button.is-active {
  border-color: #8fb5a2;
  color: var(--green-dark);
  background: var(--green-soft);
}
</style>
