<script setup lang="ts">
// SeedHero: 品牌展示 + 数字跑表
// 依据: 迭代/v3/README.md Phase 3 §SeedHero
import { setInterval } from '#app/compat/interval'
import { shallowRef, watch, onMounted, onUnmounted, useNuxtApp } from '#imports'

interface Props {
  running: boolean
}

const props = defineProps<Props>()

const { $gsap } = useNuxtApp()
const gsap = $gsap!

const elapsed = shallowRef(0)
const digits = shallowRef(['0', '0', ':', '0', '0'])
let timer: ReturnType<typeof setInterval> | null = null

function fmtTime(sec: number): string[] {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return `${mm}:${ss}`.split('')
}

function setDigitRef(el: unknown, idx: number) {
  if (!(el instanceof HTMLElement)) return
  if (idx === 2) return // ':' separator, no animation
  digitRefs.value.set(idx, el)
}

const digitRefs = shallowRef<Map<number, HTMLElement>>(new Map())

function animateDigit(el: HTMLElement) {
  if (!gsap) return
  gsap.fromTo(el,
    { scale: 0.5, opacity: 0 },
    { scale: 1.2, opacity: 1, duration: 0.15, ease: 'power2.out' },
  )
  gsap.to(el,
    { scale: 1, duration: 0.2, delay: 0.15, ease: 'elastic.out(1, 0.4)' },
  )
}

watch(elapsed, (newVal, oldVal) => {
  const newDigits = fmtTime(newVal)
  const oldDigits = fmtTime(oldVal ?? 0)

  for (let i = 0; i < newDigits.length; i++) {
    if (newDigits[i] !== oldDigits[i]) {
      const el = digitRefs.value.get(i)
      if (el) animateDigit(el)
    }
  }
  digits.value = newDigits
})

function startStopwatch() {
  if (timer) return
  elapsed.value = 0
  timer = setInterval(() => {
    elapsed.value++
  }, 1000)
}

function stopStopwatch() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

watch(() => props.running, (v) => {
  if (v) startStopwatch()
  else stopStopwatch()
})

onMounted(() => {
  if (props.running) startStopwatch()
})

onUnmounted(() => {
  stopStopwatch()
})
</script>

<template>
  <div class="flex flex-col items-center gap-2 mb-12">
    <span class="i-ph-chart-bar-duotone text-4xl color-active" />
    <h1 class="text-2xl font-medium color-base">Quant-Fletch</h1>
    <p class="text-sm op-fade mt-2 text-center max-w-md">
      正在从 AkShare 拉取 A 股 ETF 历史数据，预计需要 2-5 分钟
    </p>
    <!-- 跑表 -->
    <div class="font-mono text-4xl tabular-nums color-base mt-4 flex items-center">
      <span
        v-for="(d, i) in digits"
        :key="i"
        :ref="(el: unknown) => setDigitRef(el, i)"
        :class="d === ':' ? 'op-fade mx-0.5' : ''"
      >
        {{ d }}
      </span>
    </div>
  </div>
</template>
