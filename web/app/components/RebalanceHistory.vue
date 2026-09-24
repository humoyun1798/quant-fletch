<script setup lang="ts">
import type { SignalResult } from '../types/signal'
import FeedbackEmptyState from '@antfu/design/components/Feedback/FeedbackEmptyState.vue'

interface Props {
  signals: SignalResult[]
}

defineProps<Props>()
</script>

<template>
  <section class="px-3 py-2">
    <h2 class="text-sm font-medium color-base mb-1">调仓历史</h2>

    <FeedbackEmptyState
      v-if="signals.length === 0"
      icon="i-ph-list-numbers-duotone"
      title="无调仓记录"
    >
      <template #hint>
        回测完成后调仓历史会出现在这里
      </template>
    </FeedbackEmptyState>

    <div v-else class="overflow-x-auto">
      <table class="w-full text-xs">
        <thead>
          <tr class="border-b border-base text-left op-fade text-micro uppercase tracking-wide">
            <th class="px-2 py-1 font-medium">日期</th>
            <th class="px-2 py-1 font-medium">持仓数</th>
            <th class="px-2 py-1 font-medium">换手率</th>
            <th class="px-2 py-1 font-medium">现金</th>
            <th class="px-2 py-1 font-medium">摘要</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in [...signals].reverse().slice(0, 20)"
            :key="s.date"
            class="border-b border-base/50 hover:bg-active transition-colors duration-100"
          >
            <td class="px-2 py-1 font-mono tabular-nums">{{ s.date }}</td>
            <td class="px-2 py-1 font-mono tabular-nums">{{ s.total_positions }}</td>
            <td class="px-2 py-1 font-mono tabular-nums">{{ (s.turnover * 100).toFixed(1) }}%</td>
            <td class="px-2 py-1 font-mono tabular-nums">{{ (s.cash_ratio * 100).toFixed(1) }}%</td>
            <td class="px-2 py-1 truncate max-w-[300px]" :title="s.summary">{{ s.summary }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
