import { defineNuxtRouteMiddleware, navigateTo } from '#imports'

export default defineNuxtRouteMiddleware(async (to) => {
  // 已在 setup 页则不拦截
  if (to.path === '/setup') return

  // 开发环境未启动后端时跳过检查，避免无限重定向
  try {
    const { $fetch } = await import('#build/fetch.mjs')
    const { data } = await $fetch<{ data: { status: string } }>('/api/v1/system/status')
    if (data.status !== 'ready') {
      return navigateTo('/setup')
    }
  }
  catch {
    // API 不可用：开发阶段静默放行
    if (import.meta.dev) return
    return navigateTo('/setup')
  }
})
