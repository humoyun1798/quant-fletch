<script setup lang="ts">
import { shallowRef, watch, onMounted, onUnmounted, nextTick, useNuxtApp } from '#imports'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { useETFData } from '../composables/useETFData'
import { useMotion } from '../composables/useMotion'
import type { ETF } from '../types/etf'

const { etfs, fetchAll } = useETFData()
const { safeGsap } = useMotion()
const { $gsap } = useNuxtApp()
const gsap = $gsap!

const containerRef = shallowRef<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

function buildOption(): EChartsOption {
  const types = ['broad', 'sector', 'bond', 'commodity'] as const
  const typeLabel: Record<string, string> = {
    broad: '宽基',
    sector: '行业',
    bond: '债券',
    commodity: '商品',
  }

  const yLabels = types.map(t => typeLabel[t])
  const grouped = types.map(t => etfs.value.filter(e => e.type === t))
  const maxCols = Math.max(...grouped.map(g => g.length), 1)

  // 构造 x 轴标签：全部 ETF code 去重后按列排
  const allCodes = grouped.flat().map(e => e.code)
  const xAxisLabels = allCodes.slice(0, maxCols)

  // series data — 每项嵌入 etf 对象让 formatter 直接取用，避免闭包索引
  const heatData: Array<{ value: [number, number, number]; etf: (typeof etfs.value)[number] }> = []
  grouped.forEach((group, typeIdx) => {
    group.forEach((etf, colIdx) => {
      heatData.push({ value: [colIdx, typeIdx, etf.change_pct ?? 0], etf })
    })
  })

  const maxAbs = Math.max(...heatData.map(d => Math.abs(d.value[2])), 0.01)

  return {
    tooltip: {
      position: 'top',
      formatter: ((params: { data?: { etf?: ETF } }) => {
        const etf = params.data?.etf
        if (!etf) return ''
        return `${etf.code} ${etf.name}<br/>${(etf.latest_close ?? 0).toFixed(3)}<br/>涨跌: ${(etf.change_pct ?? 0) > 0 ? '+' : ''}${(etf.change_pct ?? 0).toFixed(2)}%`
      }) as unknown as echarts.TooltipComponentFormatterCallback<unknown>,
    },
    grid: {
      left: 56,
      right: 16,
      top: 8,
      bottom: 40,
    },
    xAxis: {
      type: 'category',
      data: xAxisLabels,
      axisLabel: { fontSize: 9, color: '#888888', rotate: 45 },
      position: 'bottom',
      splitArea: { show: true },
    },
    yAxis: {
      type: 'category',
      data: yLabels as string[],
      axisLabel: { fontSize: 10, color: '#888888' },
      splitArea: { show: true },
    },
    visualMap: {
      min: -maxAbs,
      max: maxAbs,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      // A-share convention: 涨红跌绿 (positive=red, negative=green)
      inRange: {
        color: ['#22C45D', '#f5f5f5', '#EF4444'],
      },
      text: ['涨', '跌'],
      textStyle: { color: '#888888', fontSize: 10 },
    },
    series: [
      {
        type: 'heatmap',
        data: heatData as unknown as echarts.HeatmapSeriesOption['data'],
        label: {
          show: true,
          fontSize: 10,
          color: '#888888',
          fontFamily: 'DM Mono',
          formatter: ((params: { data?: { etf?: ETF } }) => {
            const etf = params.data?.etf
            if (!etf || etf.change_pct == null) return ''
            return `${etf.change_pct > 0 ? '+' : ''}${etf.change_pct.toFixed(1)}%`
          }) as unknown as echarts.TooltipComponentFormatterCallback<unknown>,
        },
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' },
        },
      },
    ] as unknown as echarts.SeriesOption[],
  }
}

function createOrUpdate() {
  if (!containerRef.value) return
  if (!chart) {
    chart = echarts.init(containerRef.value, null, { devicePixelRatio: window.devicePixelRatio })
  }
  chart.setOption(buildOption(), true)

  // 螺旋入场: chart 容器从右下角旋转放大进入
  safeGsap(() => {
    if (!containerRef.value || !gsap) return undefined
    gsap.fromTo(containerRef.value,
      { scale: 0.3, opacity: 0, rotation: 15, transformOrigin: '100% 100%' },
      { scale: 1, opacity: 1, rotation: 0, duration: 0.7, ease: 'back.out(1.4)' },
    )
    return undefined
  })
}

function handleResize() {
  chart?.resize()
}

onMounted(async () => {
  await fetchAll()
  await nextTick()
  createOrUpdate()
  window.addEventListener('resize', handleResize)
})

watch(etfs, () => {
  if (etfs.value.length > 0) createOrUpdate()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<template>
  <section class="p-3 border-b border-base">
    <h2 class="text-sm font-medium color-base mb-2">ETF 热力图</h2>
    <div
      v-if="etfs.length === 0"
      class="border border-base rounded flex items-center justify-center min-h-[200px]"
    >
      <p class="text-xs op-fade">加载 ETF 数据中...</p>
    </div>
    <div
      v-else
      ref="containerRef"
      class="border border-base rounded w-full"
      style="height: 300px"
    />
  </section>
</template>
