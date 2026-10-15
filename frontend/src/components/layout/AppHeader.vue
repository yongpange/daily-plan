<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useSettingsStore } from '../../stores/settings'

const route = useRoute()
const settingsStore = useSettingsStore()

const navItems = [
  { name: 'today', label: '今日' },
  { name: 'report', label: '复盘' },
  { name: 'memos', label: '感悟库' },
]

const displayName = computed(() => settingsStore.profile.display_name || '未命名')
const avatarText = computed(() => displayName.value.slice(0, 1))
const avatarSrc = computed(() => settingsStore.profile.avatar_data || '')
</script>

<template>
  <header class="app-header">
    <a class="brand" href="/today">
      <span class="brand-mark">今</span>
      <span>
        <strong>每日计划</strong>
        <small>计划 · 计时 · 复盘</small>
      </span>
    </a>
    <nav class="main-nav" aria-label="主导航">
      <RouterLink
        v-for="item in navItems"
        :key="item.name"
        v-slot="{ navigate }"
        :to="`/${item.name}`"
        custom
      >
        <button
          type="button"
          class="nav-button"
          :class="{ 'is-active': route.name === item.name }"
          @click="navigate"
        >
          {{ item.label }}
        </button>
      </RouterLink>
    </nav>
    <div class="header-tools">
      <RouterLink v-slot="{ navigate }" to="/settings" custom>
        <button type="button" class="profile-button" @click="navigate">
          <span class="header-avatar">
            <img v-if="avatarSrc" :src="avatarSrc" alt="头像" />
            <template v-else>{{ avatarText }}</template>
          </span>
          <span>{{ displayName }}</span>
        </button>
      </RouterLink>
      <div class="storage-status" aria-label="本地存储状态">
        <span class="status-dot"></span>
        <span>本地 SQLite</span>
      </div>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  position: sticky;
  z-index: 30;
  top: 0;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  min-height: 56px;
  padding: 6px 24px;
  border-bottom: 1px solid rgba(218, 226, 221, 0.85);
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(14px);
}

.brand {
  display: inline-flex;
  align-items: center;
  justify-self: start;
  gap: 11px;
  color: var(--ink);
  text-decoration: none;
}

.brand-mark {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 12px;
  color: #fff;
  background: var(--green);
  box-shadow: 0 8px 18px rgba(47, 112, 84, 0.2);
  font-size: 18px;
  font-weight: 800;
}

.brand strong,
.brand small {
  display: block;
}

.brand strong {
  font-size: 15px;
}

.brand small {
  margin-top: 2px;
  color: var(--muted);
  font-size: 11px;
}

.main-nav {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 4px;
  border-radius: 11px;
  background: var(--soft);
}

.nav-button {
  min-width: 74px;
  height: 34px;
  border: 0;
  border-radius: 8px;
  color: var(--muted);
  background: transparent;
  font-weight: 650;
}

.nav-button.is-active {
  color: var(--ink);
  background: #fff;
  box-shadow: 0 2px 8px rgba(34, 51, 43, 0.08);
}

.header-tools {
  display: flex;
  align-items: center;
  justify-self: end;
  gap: 14px;
}

.profile-button {
  display: inline-flex;
  align-items: center;
  max-width: 180px;
  height: 38px;
  gap: 8px;
  padding: 0 10px 0 4px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--ink);
  background: #fff;
}

.profile-button span:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 700;
}

.header-avatar,
.avatar-preview {
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: 50%;
  color: #8a5a12;
  background: #fff4d9;
  font-weight: 800;
}

.header-avatar {
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
}

.header-avatar img,
.avatar-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.storage-status {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--muted);
  font-size: 12px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #48a979;
  box-shadow: 0 0 0 4px rgba(72, 169, 121, 0.12);
}
</style>
