// @env browser
// GSAP plugin: MorphSVG + DrawSVG + prefers-reduced-motion 全局处理
// MorphSVGPlugin/DrawSVGPlugin 需要 Club GSAP, 未订阅时优雅降级
import { defineNuxtPlugin } from '#imports'
import { gsap } from 'gsap'
import type { gsap as GSAPType } from 'gsap'

// Club GSAP plugins, import 失败时跳过
try {
  const { MorphSVGPlugin } = await import('gsap/MorphSVGPlugin')
  const { DrawSVGPlugin } = await import('gsap/DrawSVGPlugin')
  gsap.registerPlugin(MorphSVGPlugin, DrawSVGPlugin)
}
catch {
  // Club GSAP not available, basic GSAP only
}

export default defineNuxtPlugin<{ gsap: typeof GSAPType | null, gsapLowPerf: boolean }>(() => {
  if (import.meta.server) {
    return {
      provide: {
        gsap: null,
        gsapLowPerf: true,
      },
    }
  }

  // prefers-reduced-motion 全局处理
  const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
  if (mq.matches) {
    gsap.globalTimeline.timeScale(0)
  }
  mq.addEventListener('change', (e: MediaQueryListEvent) => {
    gsap.globalTimeline.timeScale(e.matches ? 0 : 1)
  })

  // 低性能设备降级
  const isLowPerf = typeof navigator !== 'undefined'
    && (navigator.hardwareConcurrency ?? 8) < 4

  return {
    provide: {
      gsap,
      gsapLowPerf: isLowPerf,
    },
  }
})
