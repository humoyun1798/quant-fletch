<script setup lang="ts">
import { computed } from '#imports'
import { useBacktest } from '../composables/useBacktest'
import { useRouter } from '#app/composables/router'
import type { Signal } from '../types/signal'
import FeedbackSkeleton from '@antfu/design/components/Feedback/FeedbackSkeleton.vue'
import FeedbackTip from '@antfu/design/components/Feedback/FeedbackTip.vue'
import FeedbackEmptyState from '@antfu/design/components/Feedback/FeedbackEmptyState.vue'
import ActionButton from '@antfu/design/components/Action/ActionButton.vue'
import DisplayNumber from '@antfu/design/components/Display/DisplayNumber.vue'
import DisplayProportionBar from '@antfu/design/components/Display/DisplayProportionBar.vue'
import LayoutCard from '@antfu/design/components/Layout/LayoutCard.vue'
import type { ProportionSegment } from '@antfu/design/components/Display/DisplayProportionBar.vue'

const router = useRouter()
const { status, result, error } = useBacktest()

const latestSignals = computed<Signal[]>(() => {
  const signals = result.value?.signals
  if (!signals || signals.length === 0) return []
  return signals[signals.length - 1].signals.filter(s => s.action !== 'sell')
})

const hasResult = computed(() => result.value != null && latestSignals.value.length > 0)
const isLoading = computed(() => status.value === 'running')

function weightSegments(w: number): ProportionSegment[] {
  return [
    { value: w, label: 'target', color: 'var(--un-color-primary)' },
    { value: 1 - w, label: 'rest', color: 'transparent' },
  ]
}
</script>

<template>
  <LayoutCard>
    <h2 class="text-sm font-medium color-base mb-2">Current Positions</h2>

    <FeedbackSkeleton v-if="isLoading" variant="text" :lines="3" />

    <div v-else-if="error" class="flex items-start gap-2">
      <FeedbackTip type="error" class="flex-1">{{ error }}</FeedbackTip>
    </div>

    <FeedbackEmptyState
      v-else-if="!hasResult"
      icon="i-ph-chart-bar-duotone"
      title="还没有回测结果"
    >
      <template #hint>
        去策略工作室跑一次回测，持仓数据自动出现在这里
      </template>
      <template #actions>
        <ActionButton variant="primary" @click="router.push('/strategy')">
          前往策略工作室
        </ActionButton>
      </template>
    </FeedbackEmptyState>

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
            <td class="px-2 py-1 text-right">
              <div class="flex items-center justify-end gap-2">
                <DisplayProportionBar
                  :segments="weightSegments(s.target_weight)"
                  :height="6"
                  class="w-16 shrink-0"
                />
                <DisplayNumber
                  :value="s.target_weight * 100"
                  :options="{ minimumFractionDigits: 1, maximumFractionDigits: 1 }"
                  suffix="%"
                />
              </div>
            </td>
            <td class="px-2 py-1 text-right">
              <DisplayNumber
                :value="s.confidence * 100"
                :options="{ minimumFractionDigits: 0, maximumFractionDigits: 0 }"
                suffix="%"
              />
            </td>
            <td class="px-2 py-1 truncate max-w-[200px]" :title="s.reason">{{ s.reason }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </LayoutCard>
</template>
