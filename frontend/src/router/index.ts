import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/today' },
    { path: '/today', name: 'today', component: () => import('../components/today/TodayView.vue') },
    { path: '/report', name: 'report', component: () => import('../components/report/ReportView.vue') },
    { path: '/memos', name: 'memos', component: () => import('../components/memos/MemosView.vue') },
    { path: '/settings', name: 'settings', component: () => import('../components/settings/SettingsView.vue') },
  ],
})

export default router
