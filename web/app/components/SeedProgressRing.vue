<script setup lang="ts">
// SeedProgressRing: SVG 环形进度 + drawSVG 动画
// 依据: 迭代/v3/README.md Phase 3 §SeedProgressRing
import { computed, shallowRef, watch, onMounted, useNuxtApp } from '#imports'

interface Props {
  current: number
  total: number
}

const props = defineProps<Props>()

const { $gsap } = useNuxtApp()
const gsap = $gsap!

const radius = 75
const strokeWidth = 10
const circumference = 2 * Math.PI * radius
const svgSize = (radius + strokeWidth) * 2

const progressPct = computed(() => {
  if (props.total === 0) return 0
  return Math.min(props.current / props.total, 1)
})

const dashOffset = computed(() => circumference * (1 - progressPct.value))

const ringRef = shallowRef<SVGCircleElement>()

function animateRing() {
  if (!gsap || !ringRef.value) return
  // Try DrawSVGPlugin if available
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const DrawSVGPlugin = (gsap as any).plugins?.drawSVG
    if (DrawSVGPlugin) {
      gsap.fromTo(ringRef.value,
        { drawSVG: 0 },
        { drawSVG: `${progressPct.value * 100}%`, duration: 0.5, ease: 'power2.out' },
      )
      return
    }
  }
  catch { /* DrawSVGPlugin not available, fallback to CSS transition */ }
  // Fallback: CSS transition via stroke-dashoffset (applied reactively)
}

watch(() => props.current, () => {
  animateRing()
})

onMounted(() => {
  animateRing()
})
</script>

<template>
  <div class="relative flex items-center justify-center" :style="{ width: `${svgSize}px`, height: `${svgSize}px` }">
    <svg
      :width="svgSize"
      :height="svgSize"
      :viewBox="`0 0 ${svgSize} ${svgSize}`"
      class="transform -rotate-90"
    >
      <!-- 背景环 -->
      <circle
        :cx="svgSize / 2"
        :cy="svgSize / 2"
        :r="radius"
        fill="none"
        :stroke-width="strokeWidth"
        class="stroke-#8882/30"
      />
      <!-- 进度环 -->
      <circle
        ref="ringRef"
        :cx="svgSize / 2"
        :cy="svgSize / 2"
        :r="radius"
        fill="none"
        :stroke-width="strokeWidth"
        stroke-linecap="round"
        class="stroke-primary-400"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="dashOffset"
        style="transition: stroke-dashoffset 0.5s ease"
      />
    </svg>
    <!-- 中心文字 -->
    <div class="absolute inset-0 flex items-center justify-center">
      <span class="font-mono text-2xl tabular-nums color-base">
        {{ current }}<span class="text-sm op-fade">/{{ total }}</span>
      </span>
    </div>
  </div>
</template>
