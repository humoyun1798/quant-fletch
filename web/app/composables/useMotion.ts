// @env browser
// GSAP 动效封装: page transition + countUp + staggerList + safeGsap + metricsBounce
import { useNuxtApp } from '#imports'
import { usePreferredReducedMotion } from '@vueuse/core'

export function useMotion() {
  const { $gsap } = useNuxtApp()
  const gsap = $gsap!
  const prefersReduced = usePreferredReducedMotion()

  function safeGsap<T>(callback: () => T): T | undefined {
    if (prefersReduced.value) {
      // reduced-motion 时不调 timeScale(0) 避免影响其他实例
      return undefined
    }
    return callback()
  }

  function pageEnter(el: Element, done: () => void) {
    if (prefersReduced.value || !el || !gsap) {
      // 跳过动画: 异步 done() 避免 Vue leave hook 同步周期内触发 performRemove
      if (el) requestAnimationFrame(() => done())
      return
    }
    gsap.fromTo(el,
      { opacity: 0, y: 12 },
      { opacity: 1, y: 0, duration: 0.35, ease: 'power3.out', onComplete: done },
    )
  }

  function pageLeave(el: Element, done: () => void) {
    if (prefersReduced.value || !el || !gsap) {
      // 跳过动画: 异步 done() 避免 Vue leave hook 同步周期内触发 performRemove
      if (el) requestAnimationFrame(() => done())
      return
    }
    gsap.to(el,
      { opacity: 0, y: -8, duration: 0.15, ease: 'power2.in', onComplete: done },
    )
  }

  function countUp(el: Element, target: number, duration = 0.8) {
    if (prefersReduced.value || !el || !gsap) {
      if (el) el.textContent = target.toLocaleString()
      return
    }
    gsap.fromTo(el,
      { textContent: 0 },
      {
        textContent: target,
        duration,
        ease: 'power2.out',
        snap: { textContent: 1 },
        onUpdate() {
          if (typeof target === 'number' && target % 1 !== 0) {
            el.textContent = Number(this.targets()[0].textContent).toFixed(2)
          }
        },
      },
    )
  }

  function staggerList(targets: string | NodeListOf<Element> | Element[], stagger = 0.04) {
    if (prefersReduced.value || !gsap) return
    const elements = typeof targets === 'string'
      ? document.querySelectorAll(targets)
      : targets
    if (!elements || elements.length === 0) return
    gsap.fromTo(elements as unknown as Element[],
      { opacity: 0, y: 8 },
      {
        opacity: 1,
        y: 0,
        duration: 0.25,
        stagger,
        ease: 'power2.out',
      },
    )
  }

  // MetricsRow: 9 卡片逐个弹入 + 悬浮呼吸
  function metricsBounce(targets: string | NodeListOf<Element> | Element[]) {
    if (prefersReduced.value || !gsap) return
    const elements = typeof targets === 'string'
      ? document.querySelectorAll(targets)
      : targets
    if (!elements || elements.length === 0) return
    gsap.from(elements as unknown as Element[],
      {
        y: 40,
        scale: 0.8,
        duration: 0.4,
        ease: 'back.out(1.7)',
        stagger: 0.06,
        onComplete() {
          gsap.to(this.targets(),
            {
              y: -1,
              duration: 1.5,
              yoyo: true,
              repeat: 1,
              ease: 'sine.inOut',
            },
          )
        },
      },
    )
  }

  // 卡片选中光脉冲
  function glowPulse(el: Element) {
    if (prefersReduced.value || !gsap) return
    gsap.fromTo(el,
      { boxShadow: '0 0 0 0px rgba(73,131,62,0.4)' },
      {
        boxShadow: '0 0 0 12px rgba(73,131,62,0)',
        duration: 0.6,
        ease: 'power2.out',
      },
    )
  }

  // 数字翻牌: 值变化时 scale 弹跳
  function numberBounce(el: Element) {
    if (prefersReduced.value || !gsap) return
    gsap.fromTo(el,
      { scale: 0.7, opacity: 0.4 },
      { scale: 1.05, opacity: 1, duration: 0.2, ease: 'back.out(2)' },
    )
    gsap.to(el, { scale: 1, duration: 0.15, delay: 0.2, ease: 'power2.out' })
  }

  return {
    pageEnter, pageLeave, countUp, staggerList,
    safeGsap, metricsBounce, glowPulse, numberBounce,
  }
}
