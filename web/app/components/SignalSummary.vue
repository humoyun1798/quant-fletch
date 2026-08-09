<script setup lang="ts">
import { useRouter } from '#imports'
import type { SignalResult } from '../types/signal'
import EmptyState from './EmptyState.vue'

interface Props {
  signals: SignalResult[]
}

defineProps<Props>()
</script>

<template>
  <section class="p-3 border-b border-base">
    <h2 class="text-sm font-medium color-base mb-2">Signal Summary</h2>
    <EmptyState
      v-if="signals.length === 0"
      icon="i-ph-arrow-left-right-duotone"
      title="先跑回测，信号自动出现在这里"
      description="回测完成后所有调仓信号会按时间线展示"
      action-label="前往策略工作室"
      @action="useRouter().push('/strategy')"
    />
    <div v-else class="text-xs op-fade font-mono tabular-nums">
      {{ signals.length }} rebalance events recorded
    </div>
  </section>
</template>
