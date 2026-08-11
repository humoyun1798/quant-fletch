<script setup lang="ts">
import { computed, useRouter } from '#imports'
import type { SignalResult } from '../types/signal'
import FeedbackEmptyState from '@antfu/design/components/Feedback/FeedbackEmptyState.vue'
import ActionButton from '@antfu/design/components/Action/ActionButton.vue'

interface Props {
  signals: SignalResult[]
}

const props = defineProps<Props>()
const router = useRouter()

const latest = computed(() => {
  if (props.signals.length === 0) return null
  return props.signals[props.signals.length - 1]
})

const buyCount = computed(() => {
  if (!latest.value) return 0
  return latest.value.signals.filter(s => s.action === 'buy').length
})

const sellCount = computed(() => {
  if (!latest.value) return 0
  return latest.value.signals.filter(s => s.action === 'sell').length
})

const maxWeight = computed(() => {
  if (!latest.value || latest.value.signals.length === 0) return null
  return latest.value.signals.reduce((a, b) =>
    a.target_weight > b.target_weight ? a : b,
  )
})

function fmtPct(val: number): string {
  return `${(val * 100).toFixed(1)}%`
}
</script>

<template>
  <section class="p-3 border-b border-base">
    <h2 class="text-sm font-medium color-base mb-2">Signal Summary</h2>

    <FeedbackEmptyState
      v-if="signals.length === 0"
      icon="i-ph-chart-line-duotone"
      title="暂无信号"
    >
      <template #hint>
        先跑回测，信号自动出现在这里
      </template>
      <template #actions>
        <ActionButton variant="primary" @click="router.push('/strategy')">
          前往策略工作室
        </ActionButton>
      </template>
    </FeedbackEmptyState>

    <div v-else class="space-y-2">
      <!-- 调仓日期 -->
      <div class="flex items-baseline gap-2">
        <span class="text-xs op-fade">最近调仓</span>
        <span class="font-mono tabular-nums text-sm font-medium color-base">
          {{ latest!.date }}
        </span>
        <span class="text-xs op-mute">
          买入 {{ buyCount }} 只，卖出 {{ sellCount }} 只
        </span>
      </div>

      <!-- 最大权重 ETF -->
      <div v-if="maxWeight" class="flex items-baseline gap-2">
        <span class="text-xs op-fade">最大权重</span>
        <span class="font-mono tabular-nums text-sm color-active">
          {{ maxWeight.code }}
        </span>
        <span class="text-xs op-mute">
          {{ fmtPct(maxWeight.target_weight) }}
        </span>
      </div>

      <!-- 换手率 + 现金比例 -->
      <div class="flex items-center gap-4">
        <div class="flex items-baseline gap-1.5">
          <span class="text-xs op-fade">换手率</span>
          <span class="font-mono tabular-nums text-xs color-base">
            {{ fmtPct(latest!.turnover) }}
          </span>
        </div>
        <div class="flex items-baseline gap-1.5">
          <span class="text-xs op-fade">现金比例</span>
          <span class="font-mono tabular-nums text-xs color-base">
            {{ fmtPct(latest!.cash_ratio) }}
          </span>
        </div>
      </div>

      <p class="text-micro op-mute">
        共 {{ signals.length }} 次调仓记录
      </p>
    </div>
  </section>
</template>
