<script setup lang="ts">
import { shallowRef, watch, onMounted, onUnmounted, nextTick } from '#imports'
import { createChart } from 'lightweight-charts'
import type { IChartApi, ISeriesApi, CandlestickData, HistogramData, Time } from 'lightweight-charts'
import type { OHLCV } from '../types/etf'
import { useChartTheme } from '../composables/useChartTheme'

interface Props {
  data: OHLCV[]
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  height: 400,
})

const { chartColors } = useChartTheme()

const containerRef = shallowRef<HTMLElement | null>(null)
let chart: IChartApi | null = null
let candlestick: ISeriesApi<'Candlestick'> | null = null
let volumeSeries: ISeriesApi<'Histogram'> | null = null

function toCandlestickData(data: OHLCV[]): CandlestickData[] {
  return data.map(d => ({
    time: d.date.slice(0, 10) as Time,
    open: d.open,
    high: d.high,
    low: d.low,
    close: d.close,
  }))
}

function toVolumeData(data: OHLCV[]): HistogramData[] {
  return data.map(d => ({
    time: d.date.slice(0, 10) as Time,
    value: d.volume,
    color: d.close >= d.open ? chartColors.candleUp + '44' : chartColors.candleDown + '44',
  }))
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
    },
    crosshair: {
      mode: 1,
    },
  })

  // A 股惯例：红涨绿跌
  candlestick = chart.addCandlestickSeries({
    upColor: chartColors.candleUp,
    downColor: chartColors.candleDown,
    borderUpColor: chartColors.candleUp,
    borderDownColor: chartColors.candleDown,
    wickUpColor: chartColors.wick,
    wickDownColor: chartColors.wick,
  })

  volumeSeries = chart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: '',
  })
  chart.priceScale('').applyOptions({
    scaleMargins: { top: 0.8, bottom: 0 },
  })
}

function destroyChart() {
  if (chart) {
    chart.remove()
    chart = null
    candlestick = null
    volumeSeries = null
  }
}

function setData(data: OHLCV[]) {
  if (!chart) {
    destroyChart()
    createChartInstance()
  }
  if (!candlestick || !volumeSeries) return
  // API returns DESC (newest first), lightweight-charts requires ASC (oldest first)
  const sorted = [...data].reverse()
  candlestick.setData(toCandlestickData(sorted))
  volumeSeries.setData(toVolumeData(sorted))
  chart!.timeScale().fitContent()
}

onMounted(() => {
  nextTick(() => {
    if (props.data.length > 0) setData(props.data)
  })
})

watch(
  () => props.data,
  (data) => {
    if (data.length > 0) {
      setData(data)
    }
  },
  { flush: 'post' },
)

onUnmounted(() => {
  destroyChart()
})
</script>

<template>
  <div class="border border-base rounded overflow-hidden">
    <div
      v-if="data.length === 0"
      class="flex flex-col items-center justify-center gap-2"
      :style="{ height: `${height}px` }"
    >
      <span class="i-ph-chart-line-up-duotone text-2xl op-mute" />
      <p class="text-xs op-fade">选择 ETF 查看 K 线</p>
    </div>
    <div
      v-else
      ref="containerRef"
      :style="{ height: `${height}px` }"
      class="w-full"
    />
  </div>
</template>
