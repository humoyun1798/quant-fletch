<script setup lang="ts">
import { computed } from '#imports'
import { useRouter } from '#imports'
import { useBacktest } from '../composables/useBacktest'
import type { Signal } from '../types/signal'
import EmptyState from './EmptyState.vue'

const router = useRouter()
const backtest = useBacktest()

const latestSignals = computed<Signal[]>(() => {
  const signals = backtest.result.value?.signals
  if (!signals || signals.length === 0) return []
  return signals[signals.length - 1].signals.filter(s => s.action !== 'sell')
})

const hasResult = computed(() => latestSignals.value.length > 0)
</script>

<template>
  <section class="p-3 border-b border-base">
    <h2 class="text-sm font-medium color-base mb-2">Current Positions</h2>

    <EmptyState
      v-if="!hasResult"
      icon="i-ph-chart-bar-duotone"
      title="还没有回测结果"
      description="去策略工作室跑一次回测，持仓数据自动出现在这里"
      action-label="前往策略工作室"
      @action="router.push('/strategy')"
    />

    <div v-else class="overflow-x-auto">
      <table class="w-full text-xs">
        <thead>
          <tr class="border-b border-base text-left op-fade text-micro uppercase tracking-wide">
            <th class="px-2 py-1 font-medium font-mono">Code</th>
            <th class="px-2 py-1 font-medium font-mono text-right">Weight</th>
            <th class="px-2 py-1 font-medium font-mono text-right">Confidence</th>
            <th class="px-2 py-1 font-medium">Reason</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in latestSignals"
            :key="s.code"
            class="border-b border-base/50 hover:bg-active transition-colors duration-100"
          >
            <td class="px-2 py-1 font-mono tabular-nums">
              <span class="px-1 py-px rounded text-micro border border-base op-fade uppercase tracking-wide">
                {{ s.action }}
              </span>
              <span class="ml-1.5">{{ s.code }}</span>
            </td>
            <td class="px-2 py-1 font-mono tabular-nums text-right">{{ (s.target_weight * 100).toFixed(1) }}%</td>
            <td class="px-2 py-1 font-mono tabular-nums text-right">{{ (s.confidence * 100).toFixed(0) }}%</td>
            <td class="px-2 py-1 truncate max-w-[200px]" :title="s.reason">{{ s.reason }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
