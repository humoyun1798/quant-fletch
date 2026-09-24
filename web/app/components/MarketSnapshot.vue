<script setup lang="ts">
import { computed, shallowRef, onMounted, watch, nextTick } from '#imports'
import { useETFData } from '../composables/useETFData'
import { useMotion } from '../composables/useMotion'
import FeedbackSkeleton from '@antfu/design/components/Feedback/FeedbackSkeleton.vue'
import FeedbackTip from '@antfu/design/components/Feedback/FeedbackTip.vue'
import DisplayNumber from '@antfu/design/components/Display/DisplayNumber.vue'
import DisplayDate from '@antfu/design/components/Display/DisplayDate.vue'
import DisplayProportionBar from '@antfu/design/components/Display/DisplayProportionBar.vue'
import LayoutCard from '@antfu/design/components/Layout/LayoutCard.vue'
import type { ProportionSegment } from '@antfu/design/components/Display/DisplayProportionBar.vue'

const { etfs, loading, error, fetchAll } = useETFData()
const { numberBounce } = useMotion()
const mounted = shallowRef(false)

onMounted(async () => {
  await fetchAll()
  mounted.value = true
})

const total = computed(() => etfs.value.length)
const hasData = computed(() => etfs.value.filter(e => e.latest_close != null).length)
const latestDate = computed(() => {
  const dates = etfs.value
    .map(e => e.latest_date)
    .filter((d): d is string => d != null)
    .sort()
  return dates.length > 0 ? dates[dates.length - 1] : null
})

const upCount = computed(() => etfs.value.filter(e => (e.change_pct ?? 0) > 0).length)
const downCount = computed(() => etfs.value.filter(e => (e.change_pct ?? 0) < 0).length)
const flatCount = computed(() => etfs.value.filter(e => (e.change_pct ?? 0) === 0).length)

const proportionSegments = computed<ProportionSegment[]>(() => [
  { value: upCount.value, label: '上涨', color: '#EF4444' },
  { value: downCount.value, label: '下跌', color: '#22C45D' },
  { value: flatCount.value, label: '平盘', color: '#888888' },
])

// 翻牌动画: 数字变化时 scale 弹跳
const hasDataRef = shallowRef<HTMLElement | null>(null)
const upCountRef = shallowRef<HTMLElement | null>(null)
const downCountRef = shallowRef<HTMLElement | null>(null)

watch(hasData, () => {
  nextTick(() => {
    if (hasDataRef.value) numberBounce(hasDataRef.value)
  })
})

watch([upCount, downCount], () => {
  nextTick(() => {
    if (upCountRef.value) numberBounce(upCountRef.value)
    if (downCountRef.value) numberBounce(downCountRef.value)
  })
})
</script>

<template>
  <LayoutCard class="mb-3">
    <h2 class="text-sm font-medium color-base mb-2">市场概览</h2>

    <FeedbackSkeleton v-if="loading" variant="text" :lines="3" />
    <div v-else-if="error" class="flex items-start gap-2">
      <FeedbackTip type="error" class="flex-1">{{ error }}</FeedbackTip>
      <button class="btn-action text-sm shrink-0" @click="fetchAll()">
        <span class="i-ph-arrow-clockwise-duotone" />重试
      </button>
    </div>

    <div v-else class="space-y-3">
      <!-- 顶栏：总数 + 日期 -->
      <div class="flex items-center justify-between">
        <div class="flex items-baseline gap-1.5">
          <span ref="hasDataRef">
            <DisplayNumber :value="hasData" class="text-lg font-medium" />
          </span>
          <span class="text-xs op-fade">
            / <DisplayNumber :value="total" class="text-xs" /> 只 ETF
          </span>
        </div>
        <DisplayDate
          v-if="latestDate"
          v-slot="{ exact }"
          :date="latestDate"
          live
          colorize
          class="text-xs op-mute font-mono tabular-nums"
        >
          {{ exact }}
        </DisplayDate>
      </div>

      <!-- 涨跌统计 -->
      <div class="flex items-center gap-4 text-xs">
        <div class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full bg-down shrink-0" />
          <span class="op-fade">上涨</span>
            <span ref="upCountRef">
              <DisplayNumber :value="upCount" class="font-medium" />
            </span>
        </div>
        <div class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full bg-up shrink-0" />
          <span class="op-fade">下跌</span>
            <span ref="downCountRef">
              <DisplayNumber :value="downCount" class="font-medium" />
            </span>
        </div>
        <div v-if="flatCount > 0" class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full border border-base shrink-0" />
          <span class="op-fade">平盘</span>
          <DisplayNumber :value="flatCount" />
        </div>
      </div>

      <!-- 涨跌比 -->
      <DisplayProportionBar :segments="proportionSegments" :height="10" />
    </div>
  </LayoutCard>
</template>
