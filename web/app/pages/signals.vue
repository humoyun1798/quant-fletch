<script setup lang="ts">
import { useBacktest } from '../composables/useBacktest'
import SignalSummary from '../components/SignalSummary.vue'
import SignalTimeline from '../components/SignalTimeline.vue'
import FeedbackEmptyState from '@antfu/design/components/Feedback/FeedbackEmptyState.vue'

const backtest = useBacktest()
</script>

<template>
  <div class="signals-view flex-1 overflow-y-auto scroll-touch">
    <template v-if="backtest.result.value?.signals && backtest.result.value.signals.length > 0">
      <SignalSummary :signals="backtest.result.value.signals" />
      <SignalTimeline :signals="backtest.result.value.signals" />
    </template>

    <section v-else-if="backtest.status.value === 'running' || backtest.status.value === 'queued'" class="p-6">
      <FeedbackEmptyState
        icon="i-ph-circle-notch-duotone animate-spin"
        title="回测运行中"
      >
        <template #hint>
          {{ `${backtest.currentStep.value || 'preparing'} ${backtest.progress.value > 0 ? Math.round(backtest.progress.value * 100) + '%' : ''}` }}
        </template>
      </FeedbackEmptyState>
    </section>

    <section v-else class="p-6">
      <FeedbackEmptyState
        icon="i-ph-arrow-left-right-duotone"
        title="先跑回测，信号自动出现在这里"
      >
        <template #hint>
          切换到 Strategy 页运行回测，完成后返回此页查看全部调仓信号按时间线展示
        </template>
      </FeedbackEmptyState>
    </section>
  </div>
</template>
