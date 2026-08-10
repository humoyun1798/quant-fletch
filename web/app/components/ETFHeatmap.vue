<script setup lang="ts">
import { shallowRef, watch, onMounted, onUnmounted, nextTick } from '#imports'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { useETFData } from '../composables/useETFData'
import type { ETF } from '../types/etf'

const { etfs, fetchAll } = useETFData()
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
      heatData.push({ value: [colIdx, typeIdx, etf.change_pct], etf })
    })
  })

  const maxAbs = Math.max(...heatData.map(d => Math.abs(d.value[2])), 0.01)

  return {
    tooltip: {
      position: 'top',
      formatter: (params: { data?: { etf?: ETF } }) => {
        const etf = params.data?.etf
        if (!etf) return ''
        return `${etf.code} ${etf.name}<br/>${etf.latest_close.toFixed(3)}<br/>涨跌: ${etf.change_pct > 0 ? '+' : ''}${etf.change_pct.toFixed(2)}%`
      },
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
      data: yLabels,
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
      inRange: {
        color: ['#cf1322', '#f5f5f5', '#49833E'],
      },
      text: ['涨', '跌'],
      textStyle: { color: '#888888', fontSize: 10 },
    },
    series: [
      {
        type: 'heatmap',
        data: heatData,
        label: {
          show: true,
          fontSize: 10,
          color: '#888888',
          fontFamily: 'DM Mono',
          formatter: (params: { data?: { etf?: ETF } }) => {
            const etf = params.data?.etf
            if (!etf || etf.change_pct == null) return ''
            return `${etf.change_pct > 0 ? '+' : ''}${etf.change_pct.toFixed(1)}%`
          },
        },
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' },
        },
      },
    ],
  }
}

function createOrUpdate() {
  if (!containerRef.value) return
  if (!chart) {
    chart = echarts.init(containerRef.value, null, { devicePixelRatio: window.devicePixelRatio })
  }
  chart.setOption(buildOption(), true)
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
    <h2 class="text-sm font-medium color-base mb-2">ETF Heatmap</h2>
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
