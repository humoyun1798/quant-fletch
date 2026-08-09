<script setup lang="ts">
import { shallowRef, watch, onMounted } from '#imports'
import { useMotion } from '../composables/useMotion'
import type { Metrics } from '../types/backtest'

interface Props {
  metrics: Metrics | null
}

const props = defineProps<Props>()
const { metricsBounce, countUp, safeGsap } = useMotion()

const gridRef = shallowRef<HTMLElement>()
const valueRefs = shallowRef<Map<string, HTMLElement>>(new Map())

const metricCards: Array<{ key: keyof Metrics, label: string, format: 'pct' | 'ratio' | 'days' }> = [
  { key: 'total_return', label: 'Total Return', format: 'pct' },
  { key: 'annual_return', label: 'Annual Return', format: 'pct' },
  { key: 'annual_volatility', label: 'Annual Vol', format: 'pct' },
  { key: 'sharpe_ratio', label: 'Sharpe', format: 'ratio' },
  { key: 'max_drawdown', label: 'Max DD', format: 'pct' },
  { key: 'calmar_ratio', label: 'Calmar', format: 'ratio' },
  { key: 'win_rate', label: 'Win Rate', format: 'pct' },
  { key: 'benchmark_return', label: 'Benchmark', format: 'pct' },
  { key: 'alpha', label: 'Alpha', format: 'ratio' },
  { key: 'avg_turnover', label: 'Turnover', format: 'ratio' },
]

function fmt(val: number, format: 'pct' | 'ratio' | 'days'): string {
  if (format === 'pct') return `${(val * 100).toFixed(2)}%`
  if (format === 'ratio') return val.toFixed(2)
  return String(val)
}

function colorClass(val: number, key: string): string {
  if (key.includes('drawdown') || key.includes('volatility')) {
    return val < 0 ? 'color-#EF4444' : 'color-#22C45D'
  }
  return val > 0 ? 'color-#EF4444' : val < 0 ? 'color-#22C45D' : 'op-fade'
}

function setValueRef(key: string, el: unknown) {
  if (el instanceof Element) valueRefs.value.set(key, el as HTMLElement)
}

// watch metrics: 数据就绪后触发弹入动画 + 数字滚动
watch(() => props.metrics, (m) => {
  if (!m) return
  // nextTick-like delay to ensure DOM is painted before animating
  safeGsap(() => {
    if (gridRef.value) {
      metricsBounce(gridRef.value.querySelectorAll('.metric-card'))
    }
    // countUp on each value element
    setTimeout(() => {
      for (const mc of metricCards) {
        const el = valueRefs.value.get(mc.key)
        if (el && m[mc.key] != null) {
          el.textContent = ''
          countUp(el, m[mc.key] ?? 0)
        }
      }
    }, 100)
    return undefined
  })
})
</script>

<template>
  <section class="p-3">
    <h2 class="text-sm font-medium color-base mb-2">Performance Metrics</h2>

    <!-- Empty state -->
    <div v-if="!metrics" class="grid grid-cols-3 md:grid-cols-5 gap-2">
      <div
        v-for="mc in metricCards"
        :key="mc.key"
        class="px-2 py-1.5 border border-base border-dashed rounded text-center"
      >
        <p class="text-micro op-mute">{{ mc.label }}</p>
        <p class="text-xs font-mono op-mute">---</p>
      </div>
    </div>

    <!-- Data state -->
    <div v-else ref="gridRef" class="grid grid-cols-3 md:grid-cols-5 gap-2">
      <div
        v-for="mc in metricCards"
        :key="mc.key"
        class="metric-card px-2 py-1.5 border border-base rounded text-center"
      >
        <p class="text-micro op-mute">{{ mc.label }}</p>
        <p
          :ref="(el: unknown) => setValueRef(mc.key, el)"
          class="text-sm font-mono tabular-nums"
          :class="colorClass(metrics[mc.key] ?? 0, mc.key)"
        >
          {{ fmt(metrics[mc.key] ?? 0, mc.format) }}
        </p>
      </div>
    </div>
  </section>
</template>
