<script setup lang="ts">
// 感悟库视图 —— 平移 web-legacy/index.html L569-672（memosView）+
// app.js memoSearchTimer/clearMemoSearch/openMemoTemplates 绑定(4596-4603, 4662)
import { ref, watch } from 'vue'
import type { Memo } from '../../types/api'
import { useMemoStore } from '../../stores/memo'
import { useDialogStore } from '../../stores/dialogs'
import MemoComposePanel from './MemoComposePanel.vue'
import MemoFeed from './MemoFeed.vue'
import MemoSourceFilters from './MemoSourceFilters.vue'
import ReminderPanel from './ReminderPanel.vue'
import MemoEditDialog from '../dialogs/MemoEditDialog.vue'

const memoStore = useMemoStore()
const dialogsStore = useDialogStore()

const searchQuery = ref('')

// ---------- 搜索（平移 memoSearchTimer 300ms 防抖；来源变化重查 loadMemos） ----------
function onSearchInput() {
  const query = searchQuery.value.trim()
  memoStore.searchMemosDebounced(query, () => memoStore.loadMemos(query))
}

function clearMemoSearch() {
  searchQuery.value = ''
  void memoStore.loadMemos()
}

watch(
  () => memoStore.memoSource,
  () => void memoStore.loadMemos(searchQuery.value.trim()),
)

// ---------- 模板 ----------
const composeRef = ref<InstanceType<typeof MemoComposePanel> | null>(null)

function openMemoTemplates() {
  dialogsStore.openTemplate(composeRef.value?.templateTarget() ?? null)
}

// ---------- 编辑感悟 ----------
const editingMemo = ref<Memo | null>(null)

function openMemoEdit(memo: Memo) {
  if (memo.kind !== 'memo') return
  editingMemo.value = memo
}

function closeMemoEdit() {
  editingMemo.value = null
}
</script>

<template>
  <section class="memos-view">
    <div class="view-toolbar">
      <div>
        <p class="eyebrow">让零散发现以后找得到</p>
        <h1>感悟库</h1>
      </div>
      <div class="memo-search">
        <input
          id="memoSearchInput"
          v-model="searchQuery"
          type="search"
          maxlength="200"
          placeholder="搜索内容或标签"
          aria-label="搜索感悟"
          @input="onSearchInput"
        />
        <button id="clearMemoSearch" class="button subtle compact" @click="clearMemoSearch">
          清除
        </button>
        <button id="openMemoTemplates" type="button" class="button subtle compact" @click="openMemoTemplates">
          模板
        </button>
      </div>
    </div>

    <div class="memos-layout">
      <MemoComposePanel ref="composeRef" />

      <section class="memo-feed-section">
        <ReminderPanel />
        <MemoSourceFilters />
        <MemoFeed :query="searchQuery" @edit="openMemoEdit" />
      </section>
    </div>

    <MemoEditDialog :memo="editingMemo" @close="closeMemoEdit" />
  </section>
</template>

<style scoped>
/* 平移 web-legacy/styles.css L2240-2248（memo-search）与 L2250-2274（memos-layout） */
.memo-search {
  display: flex;
  align-items: center;
  gap: 8px;
}

.memo-search input {
  width: min(320px, 50vw);
}

.memos-layout {
  display: grid;
  grid-template-columns: minmax(280px, 0.65fr) minmax(0, 1.35fr);
  align-items: start;
  gap: 18px;
}

.memo-feed-section {
  display: grid;
  gap: 14px;
  min-width: 0;
}

@media (max-width: 960px) {
  .memos-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
