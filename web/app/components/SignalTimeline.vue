<script setup lang="ts">
import type { SignalResult } from '../types/signal'
import FeedbackEmptyState from '@antfu/design/components/Feedback/FeedbackEmptyState.vue'

interface Props {
  signals: SignalResult[]
}

defineProps<Props>()
</script>

<template>
  <section class="p-3">
    <h2 class="text-sm font-medium color-base mb-2">Signal Timeline</h2>

    <FeedbackEmptyState
      v-if="signals.length === 0"
      icon="i-ph-clock-counter-clockwise-duotone"
      title="暂无信号记录"
    >
      <template #hint>
        回测运行后信号时间线会在这里展示
      </template>
    </FeedbackEmptyState>

    <div v-else class="flex flex-col gap-1">
      <div
        v-for="(s, i) in signals.slice(-30).reverse()"
        :key="s.date"
        class="flex items-start gap-3 px-2 py-1"
      >
        <div class="flex flex-col items-center shrink-0">
          <span class="font-mono tabular-nums text-micro op-fade w-[80px]">{{ s.date }}</span>
          <div class="w-px flex-1 bg-active mt-0.5" :class="{ 'op-0': i === 0 }" />
        </div>
        <div class="flex flex-col gap-0.5">
          <p class="text-xs color-base">{{ s.summary }}</p>
          <div class="flex flex-wrap gap-1">
            <span
              v-for="sig in s.signals"
              :key="sig.code"
              class="px-1 py-px rounded text-micro font-mono"
              :class="sig.action === 'buy' ? 'bg-up-soft color-up border border-up-soft' : sig.action === 'sell' ? 'bg-down-soft color-down border border-down-soft' : 'op-fade border border-base'"
            >
              {{ sig.action.toUpperCase() }} {{ sig.code }}
              <span class="op-fade">@ {{ (sig.target_weight * 100).toFixed(0) }}%</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
