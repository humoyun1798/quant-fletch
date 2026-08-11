<script setup lang="ts">
import type { Metrics } from '../types/backtest'
import DisplayNumber from '@antfu/design/components/Display/DisplayNumber.vue'

interface Props {
  metrics: Metrics | null
}

defineProps<Props>()

interface MetricDef {
  key: keyof Metrics
  label: string
  suffix: string
  decimals: number
  /** Invert color: true = positive values are bad (vol, dd). */
  invert?: boolean
}

const metricDefs: MetricDef[] = [
  { key: 'total_return', label: 'Total Return', suffix: '%', decimals: 2 },
  { key: 'annual_return', label: 'Annual Return', suffix: '%', decimals: 2 },
  { key: 'annual_volatility', label: 'Annual Vol', suffix: '%', decimals: 2, invert: true },
  { key: 'sharpe_ratio', label: 'Sharpe', suffix: '', decimals: 2 },
  { key: 'max_drawdown', label: 'Max DD', suffix: '%', decimals: 2, invert: true },
  { key: 'calmar_ratio', label: 'Calmar', suffix: '', decimals: 2 },
  { key: 'win_rate', label: 'Win Rate', suffix: '%', decimals: 1 },
  { key: 'benchmark_return', label: 'Benchmark', suffix: '%', decimals: 2 },
  { key: 'alpha', label: 'Alpha', suffix: '', decimals: 2 },
  { key: 'avg_turnover', label: 'Turnover', suffix: '', decimals: 2 },
]

function metricColor(val: number, invert?: boolean): string {
  if (invert) return val < 0 ? 'color-down' : 'color-up'
  if (val > 0) return 'color-down'
  if (val < 0) return 'color-up'
  return ''
}
</script>

<template>
  <div class="px-3 py-2">
    <h2 class="text-sm font-medium color-base mb-1">Performance Metrics</h2>

    <!-- Empty -->
    <div v-if="!metrics" class="grid grid-cols-3 md:grid-cols-5 gap-2">
      <div
        v-for="mc in metricDefs"
        :key="mc.key"
        class="px-2 py-1.5 border border-base border-dashed rounded text-center"
      >
        <p class="text-micro op-mute">{{ mc.label }}</p>
        <p class="text-xs font-mono op-mute">---</p>
      </div>
    </div>

    <!-- Data -->
    <div v-else class="grid grid-cols-3 md:grid-cols-5 gap-2">
      <div
        v-for="mc in metricDefs"
        :key="mc.key"
        class="metric-card px-2 py-1.5 border border-base rounded text-center"
      >
        <p class="text-micro op-mute mb-0.5">{{ mc.label }}</p>
        <DisplayNumber
          :value="(metrics[mc.key] ?? 0) * (mc.suffix === '%' ? 100 : 1)"
          :options="{ minimumFractionDigits: mc.decimals, maximumFractionDigits: mc.decimals }"
          :suffix="mc.suffix"
          class="text-sm"
          :class="metricColor(metrics[mc.key] ?? 0, mc.invert)"
        />
      </div>
    </div>
  </div>
</template>
