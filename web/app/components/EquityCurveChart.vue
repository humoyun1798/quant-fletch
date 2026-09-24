<script setup lang="ts">
import { shallowRef, watch, onMounted, onUnmounted, nextTick, useNuxtApp } from '#imports'
import { createChart } from 'lightweight-charts'
import type { IChartApi, ISeriesApi, LineData, Time } from 'lightweight-charts'
import { useChartTheme } from '../composables/useChartTheme'
import { useMotion } from '../composables/useMotion'

interface Props {
  data: Array<{ date: string, equity: number, benchmark: number }>
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  height: 320,
})

interface Emits {
  (e: 'ready'): void
}

const emit = defineEmits<Emits>()

const { chartColors } = useChartTheme()
const { safeGsap } = useMotion()
const { $gsap } = useNuxtApp()
const gsap = $gsap!

const containerRef = shallowRef<HTMLElement | null>(null)
const shimmerRef = shallowRef<HTMLElement | null>(null)
let chart: IChartApi | null = null
let equityLine: ISeriesApi<'Line'> | null = null
let benchmarkLine: ISeriesApi<'Line'> | null = null

function toLineData(items: Array<{ date: string, equity: number, benchmark: number }>): {
  equityData: LineData[]
  benchmarkData: LineData[]
} {
  const equityData: LineData[] = []
  const benchmarkData: LineData[] = []
  for (const d of items) {
    const time = d.date.slice(0, 10) as Time
    equityData.push({ time, value: d.equity })
    benchmarkData.push({ time, value: d.benchmark })
  }
  return { equityData, benchmarkData }
}

function createChartInstance() {
  if (!containerRef.value || chart) return

  chart = createChart(containerRef.value, {
    height: props.height,
    layout: {
      background: { color: 'transparent' },
      textColor: chartColors.text,
    },
    grid: {
      vertLines: { color: chartColors.grid },
      horzLines: { color: chartColors.grid },
    },
    timeScale: {
      borderColor: chartColors.grid,
    },
    rightPriceScale: {
      borderColor: chartColors.grid,
      scaleMargins: { top: 0.05, bottom: 0.05 },
    },
    crosshair: {
      mode: 1,
    },
  })

  equityLine = chart.addLineSeries({
    color: chartColors.equity,
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: true,
    title: '策略净值',
  })

  benchmarkLine = chart.addLineSeries({
    color: chartColors.benchmark,
    lineWidth: 1,
    lineStyle: 2, // dashed
    priceLineVisible: false,
    lastValueVisible: true,
    title: '基准净值',
  })
}

function destroyChart() {
  if (chart) {
    chart.remove()
    chart = null
    equityLine = null
    benchmarkLine = null
  }
}

function setData(items: Array<{ date: string, equity: number, benchmark: number }>) {
  if (!chart) {
    destroyChart()
    createChartInstance()
  }
  if (!equityLine || !benchmarkLine) return
  const { equityData, benchmarkData } = toLineData(items)
  equityLine.setData(equityData)
  benchmarkLine.setData(benchmarkData)
  chart!.timeScale().fitContent()
  emit('ready')

  // 光线绘制: 渐变色从左到右扫过图表
  safeGsap(() => {
    if (!shimmerRef.value || !gsap) return undefined
    const tl = gsap.timeline()
    tl.fromTo(shimmerRef.value,
      { x: '-100%', opacity: 0.8 },
      { x: '100%', duration: 0.8, ease: 'power2.inOut' },
    )
    tl.to(shimmerRef.value,
      { opacity: 0, duration: 0.2, ease: 'power2.out' },
      '-=0.1',
    )
    return undefined
  })
}

watch(
  () => props.data,
  (data) => {
    if (data.length > 0) {
      setData(data)
    }
  },
  { immediate: true, flush: 'post' },
)

onMounted(() => {
  nextTick(() => {
    if (props.data.length > 0) setData(props.data)
  })
})

onUnmounted(() => {
  destroyChart()
})
</script>

<template>
  <section class="px-3 py-2">
    <h2 class="text-sm font-medium color-base mb-1">净值曲线</h2>
    <div class="border border-base rounded overflow-hidden relative">
      <div
        v-if="data.length === 0"
        class="flex flex-col items-center justify-center gap-2"
        :style="{ height: `${height}px` }"
      >
        <span class="i-ph-chart-line-duotone text-2xl op-mute" />
        <p class="text-xs op-fade">运行回测后显示净值曲线</p>
      </div>
      <div
        v-else
        ref="containerRef"
        :style="{ height: `${height}px` }"
        class="w-full"
      />
      <!-- 光线扫过遮罩 -->
      <div
        ref="shimmerRef"
        class="absolute inset-0 pointer-events-none"
        style="background: linear-gradient(90deg, transparent 0%, rgba(124,188,113,0.12) 40%, rgba(124,188,113,0.25) 50%, rgba(124,188,113,0.12) 60%, transparent 100%);"
      />
    </div>
  </section>
</template>
