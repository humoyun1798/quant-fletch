import { defineNuxtRouteMiddleware, navigateTo, useRequestFetch } from '#imports'

export default defineNuxtRouteMiddleware(async (to) => {
  // 已在 setup 页则不拦截
  if (to.path === '/setup') return

  // 开发环境未启动后端时跳过检查，避免无限重定向
  try {
    // 注意: 这里不能用 `await import('ofetch')` 取 $fetch。那是 ofetch 的原生实现,
    // 在 SSR 阶段没有 window.location, 无法解析相对 URL (抛 Failed to parse URL),
    // 于是每次都落到 catch 分支被重定向到 /setup —— 即使数据早已就绪。
    // useRequestFetch() 在服务端会带上当前请求的上下文, 客户端等同全局 $fetch。
    const $fetch = useRequestFetch()
    const { data } = await $fetch<{ data: { status: string } }>('/api/v1/system/status')
    if (data.status !== 'ready') {
      return navigateTo('/setup')
    }
  }
  catch {
    // ⚠️ 「API 不可达」不等于「数据未初始化」, 不能都跳 /setup。
    // 原实现两者混为一谈, 后果实测过 (2026-09-21): 内网穿透一断, SSR 拿不到
    // 状态接口 → 界面直接显示"数据初始化"页 → 用户以为数据丢了并去点初始化
    // → 那个按钮走同一条断掉的链路、同样失败(502), 白折腾一场且数据其实完好。
    // 故此处只放行, 由页面自身呈现"取不到数据"的状态, 不再制造误导。
    return
  }
})
