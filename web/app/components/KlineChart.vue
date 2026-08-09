<script setup lang="ts">
import { shallowRef, watch, onMounted, onUnmounted, nextTick } from '#imports'
import { createChart } from 'lightweight-charts'
import type { IChartApi, ISeriesApi, CandlestickData, Time } from 'lightweight-charts'
import type { Bar, BarPeriod } from '../types/etf'

interface Props {
  data: Bar[]
  period?: BarPeriod
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  period: 'daily',
  height: 400,
})

const containerRef = shallowRef<HTMLElement | null>(null)
let chart: IChartApi | null = null
let candlestick: ISeriesApi<'Candlestick'> | null = null

const isIntraday = () => props.period !== 'daily'

function toCandlestickData(data: Bar[]): CandlestickData[] {
  return data.map((d) => {
    let time: Time
    if (isIntraday()) {
      // lightweight-charts 日内需要 Unix 时间戳（秒）
      time = Math.floor(new Date(d.dt).getTime() / 1000) as Time
    }
    else {
      // 日线接受 yyyy-mm-dd 字符串
      time = d.dt.slice(0, 10) as Time
    }
    return {
      time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }
  })
}

function createChartInstance() {
  if (!containerRef.value || chart) return

  const dateFmt = isIntraday() ? 'yyyy/MM/dd HH:mm' : 'yyyy/MM/dd'

  chart = createChart(containerRef.value, {
    height: props.height,
    layout: {
      background: { color: 'transparent' },
      textColor: '#8888',
    },
    grid: {
      vertLines: { color: '#8881' },
      horzLines: { color: '#8881' },
    },
    localization: {
      dateFormat: dateFmt,
    },
    timeScale: {
      borderColor: '#8882',
      timeVisible: isIntraday(),
    },
    rightPriceScale: {
      borderColor: '#8882',
    },
    crosshair: {
      mode: 0,
    },
  })

  candlestick = chart.addCandlestickSeries({
    upColor: '#49833E',
    downColor: '#cf1322',
    borderUpColor: '#49833E',
    borderDownColor: '#cf1322',
    wickUpColor: '#49833E',
    wickDownColor: '#cf1322',
  })
}

function destroyChart() {
  if (chart) {
    chart.remove()
    chart = null
    candlestick = null
  }
}

function setData(data: Bar[]) {
  if (!chart) {
    destroyChart()
    createChartInstance()
  }
  if (!candlestick) return
  candlestick.setData(toCandlestickData(data))
  chart!.timeScale().fitContent()
}

onMounted(() => {
  nextTick(() => {
    if (props.data.length > 0) setData(props.data)
  })
})

watch(
  () => props.data,
  async (data) => {
    if (data.length > 0) {
      await nextTick()
      setData(data)
    }
  },
)

watch(
  () => props.period,
  () => {
    if (props.data.length > 0) {
      destroyChart()
      nextTick(() => setData(props.data))
    }
  },
)

onUnmounted(() => {
  destroyChart()
})
</script>

<template>
  <div class="border border-base rounded overflow-hidden">
    <div v-if="data.length === 0" class="flex flex-col items-center justify-center gap-2" :style="{ height: `${height}px` }">
      <span class="i-ph-chart-candlestick-duotone text-2xl op-mute" />
      <p class="text-xs op-fade">选择 ETF 查看 K 线</p>
    </div>
    <div ref="containerRef" v-else :style="{ height: `${height}px` }" class="w-full" />
  </div>
</template>
