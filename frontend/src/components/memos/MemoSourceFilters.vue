<script setup lang="ts">
// 来源过滤 chips —— 平移 web-legacy/app.js renderMemoSources(2347)
import { useMemoStore } from '../../stores/memo'

const memoStore = useMemoStore()

function isActive(kind: string, id: number): boolean {
  const current = memoStore.memoSource
  return Boolean(current && current.kind === kind && Number(current.id) === Number(id))
}

function select(kind: string, id?: number) {
  if (kind && id != null) memoStore.openMemoSource(kind, id)
  else memoStore.clearMemoSource()
}
</script>

<template>
  <div class="memo-source-filters">
    <button
      type="button"
      class="memo-source-chip"
      :class="{ 'is-active': !memoStore.memoSource }"
      @click="select('')"
    >全部</button>
    <button
      v-for="source in memoStore.memoSources"
      :key="`${source.kind}-${source.id}`"
      type="button"
      class="memo-source-chip"
      :class="{ 'is-active': isActive(source.kind, source.id) }"
      @click="select(source.kind, source.id)"
    >
      <span>{{ source.kind === 'thread' ? '主线' : '必做' }}</span>
      {{ source.title }}
      <strong>{{ source.count }}</strong>
    </button>
  </div>
</template>

<style scoped>
.memo-source-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.memo-source-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--ink);
  background: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.memo-source-chip span {
  color: var(--muted);
  font-size: 11px;
  font-weight: 650;
}

.memo-source-chip strong {
  min-width: 1.2em;
  color: var(--green);
  font-variant-numeric: tabular-nums;
}

.memo-source-chip.is-active {
  border-color: #b7d4c4;
  background: var(--green-soft);
}
</style>
