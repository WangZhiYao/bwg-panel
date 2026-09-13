import { createRouter, createWebHistory } from 'vue-router'
import { ApiError, me } from './api'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('./views/LoginView.vue') },
    { path: '/', component: () => import('./views/DashboardView.vue') },
    { path: '/trends', component: () => import('./views/TrendsView.vue') },
    { path: '/alerts', component: () => import('./views/AlertsView.vue') },
    { path: '/settings', component: () => import('./views/SettingsView.vue') },
  ],
})

router.beforeEach(async (to) => {
  if (to.path === '/login') {
    try {
      await me()
      return '/'                                   // 已登录 → 回首页（导航前完成，不闪屏）
    } catch {
      return true
    }
  }
  try {
    await me()
    return true
  } catch (e) {
    if (e instanceof ApiError) return '/login'   // 明确未授权才踢
    return true                                   // 网络瞬断放行（页面自身容错）
  }
})

export default router
