<script setup lang="ts">
// 标签预设 chips（平移 renderTagPresets / applyTagPreset）
import { computed } from 'vue'
import { useMemoStore } from '../../stores/memo'

const props = defineProps<{
  modelValue: string
  tagInputId: string
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: string): void }>()

const memoStore = useMemoStore()

const visible = computed(() => memoStore.suggestedTags.length > 0)

function isActive(tag: string): boolean {
  return props.modelValue.split(/[,，\s]+/).some((item) => item.trim() === tag)
}

function toggle(tag: string) {
  const current = props.modelValue
    .split(/[,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
  const index = current.indexOf(tag)
  if (index >= 0) current.splice(index, 1)
  else current.push(tag)
  emit('update:modelValue', current.join(' '))
}
</script>

<template>
  <div v-if="visible" class="tag-presets" :data-tag-input="tagInputId">
    <span class="tag-presets-label">常用</span>
    <button
      v-for="tag in memoStore.suggestedTags"
      :key="tag"
      type="button"
      class="tag-preset"
      :class="{ 'is-active': isActive(tag) }"
      @click="toggle(tag)"
    >
      {{ tag }}
    </button>
  </div>
</template>

<style scoped>
.tag-presets {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}

.tag-presets-label {
  color: var(--muted);
  font-size: 12px;
}

.tag-preset {
  min-height: 26px;
  padding: 0 9px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: #4e5a55;
  background: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.tag-preset.is-active,
.tag-preset:hover {
  border-color: #8fb5a2;
  color: var(--green-dark);
  background: var(--green-soft);
}
</style>
