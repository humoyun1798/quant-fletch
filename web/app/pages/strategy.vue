<script setup lang="ts">
import { shallowRef, watch, onMounted } from '#imports'
import { useStrategy } from '../composables/useStrategy'
import { useBacktest } from '../composables/useBacktest'
import { useMotion } from '../composables/useMotion'
import type { ParamDef, StrategyMeta } from '../types/strategy'
import type { BacktestConfig } from '../types/backtest'
import StrategyCardList from '../components/StrategyCardList.vue'
import FormSegmentedControl from '@antfu/design/components/Form/FormSegmentedControl.vue'
import FormNumberInput from '@antfu/design/components/Form/FormNumberInput.vue'
import ParamSlider from '../components/ParamSlider.vue'
import BacktestTrigger from '../components/BacktestTrigger.vue'
import EquityCurveChart from '../components/EquityCurveChart.vue'
import MetricsRow from '../components/MetricsRow.vue'
import RebalanceHistory from '../components/RebalanceHistory.vue'
import FeedbackTip from '@antfu/design/components/Feedback/FeedbackTip.vue'
import FeedbackEmptyState from '@antfu/design/components/Feedback/FeedbackEmptyState.vue'
import LayoutSplitPane from '@antfu/design/components/Layout/LayoutSplitPane.vue'
import { Pane } from 'splitpanes'
import { choiceLabel, paramLabel } from '../config/labels'

const { strategies, selected, params, fetchAll, updateParam } = useStrategy()
const backtest = useBacktest()
const { staggerList, metricsBounce } = useMotion()

const selectedMeta = shallowRef<StrategyMeta | null>(null)

onMounted(async () => {
  await fetchAll()
  staggerList('.strategy-grid > *')
})

watch(selected, (name) => {
  if (name) {
    selectedMeta.value = strategies.value.find(s => s.name === name) ?? null
  }
  backtest.reset()
})

function isSliderParam(p: ParamDef): boolean {
  return (p.type === 'int' || p.type === 'float') && p.min !== undefined && p.max !== undefined
}

function isNumberParam(p: ParamDef): boolean {
  return (p.type === 'int' || p.type === 'float') && (p.min === undefined || p.max === undefined)
}

function startBacktest() {
  if (!selected.value) return
  // 刻意不传 start_date / end_date: 由后端解析默认区间
  // (start=2020-01-01, end=库中最新交易日)。原先这里硬编码
  // end_date: '2025-12-31', 导致界面回测永远看不到 2026 年的数据。
  const config: BacktestConfig = {
    strategy: selected.value,
    params: { ...params.value },
    benchmark: '510300.SH',
  }
  backtest.run(config)
}
</script>

<template>
  <div class="flex-1 flex flex-col of-hidden">

    <LayoutSplitPane class="flex-1" storage-key="strategy-split">
      <!-- 左侧面板：策略选择 + 参数 + 回测按钮 -->
      <Pane :size="35" :min-size="20">
      <div class="overflow-y-auto scroll-touch h-full">
        <StrategyCardList />

        <section v-if="selected" class="p-3 border-b border-base">
          <div class="flex items-center gap-2 mb-2">
            <h2 class="text-sm font-medium color-base">参数</h2>
            <span class="font-mono text-xs color-active">{{ selected }}</span>
          </div>

          <div class="grid grid-cols-1 gap-3">
            <template v-for="p in selectedMeta?.params ?? []" :key="p.name">
              <!-- choice → FormSegmentedControl -->
              <div v-if="p.type === 'choice' && p.choices" class="flex flex-col gap-1">
                <label class="text-xs color-base" :title="p.name">{{ paramLabel(p.name) }}</label>
                <FormSegmentedControl
                  :options="p.choices.map(c => ({ value: c, label: choiceLabel(c) }))"
                  :model-value="String(params[p.name] ?? p.default)"
                  @update:model-value="(v: string | number | null | undefined) => { if (v != null) updateParam(p.name, v) }"
                />
              </div>
              <!-- number with min/max → ParamSlider -->
              <ParamSlider
                v-else-if="isSliderParam(p)"
                :label="paramLabel(p.name)"
                :description="p.description"
                :min="p.min!"
                :max="p.max!"
                :model-value="Number(params[p.name] ?? p.default)"
                @update:model-value="(v: number | undefined) => { if (v !== undefined) updateParam(p.name, v) }"
              />
              <!-- number without min/max → FormNumberInput -->
              <div v-else-if="isNumberParam(p)" class="flex flex-col gap-1">
                <label class="text-xs color-base" :title="p.name">{{ paramLabel(p.name) }}</label>
                <FormNumberInput
                  :model-value="Number(params[p.name] ?? p.default)"
                  :step="p.type === 'int' ? 1 : 0.1"
                  @update:model-value="(v: number | undefined) => { if (v !== undefined) updateParam(p.name, v) }"
                />
              </div>
            </template>
          </div>
        </section>

        <section v-if="selected" class="p-3 border-b border-base">
          <BacktestTrigger
            :status="backtest.status.value"
            :progress="backtest.progress.value"
            :current-step="backtest.currentStep.value"
            :disabled="!selected"
            @run="startBacktest"
          />
        </section>
      </div>
      </Pane>

      <!-- 右侧面板：图表 + 指标 + 调仓历史 -->
      <Pane :size="65" :min-size="30">
      <div class="overflow-y-auto scroll-touch h-full">
        <template v-if="backtest.result.value">
          <!-- 回测区间: 由后端解析 (end 默认库中最新交易日), 显式展示避免误判为"数据缺失" -->
          <div class="px-3 pt-2 pb-1 flex items-baseline gap-1.5 text-xs">
            <span class="op-fade">回测区间</span>
            <span class="font-mono tabular-nums color-base">
              {{ backtest.result.value.start_date ?? '—' }}
            </span>
            <span class="op-fade">~</span>
            <span class="font-mono tabular-nums color-base">
              {{ backtest.result.value.end_date ?? '—' }}
            </span>
            <span class="op-mute">
              （共 {{ backtest.result.value.metrics?.n_trading_days ?? 0 }} 个交易日）
            </span>
          </div>
          <EquityCurveChart
            :data="backtest.result.value.equity_curve"
            @ready="metricsBounce('.metrics-row > *')"
          />
          <hr class="border-base/30 mx-3">
          <div class="metrics-row">
            <MetricsRow :metrics="backtest.result.value.metrics" />
          </div>
          <hr class="border-base/30 mx-3">
          <RebalanceHistory :signals="backtest.result.value.signals" />
        </template>

        <section v-else-if="backtest.status.value === 'completed' || backtest.status.value === 'failed'" class="p-3">
          <div v-if="backtest.error.value" class="flex items-start gap-2">
            <FeedbackTip type="error" class="flex-1">
              {{ backtest.error.value }}
            </FeedbackTip>
            <button class="btn-action text-sm shrink-0" @click="startBacktest()">
              <span class="i-ph-arrow-clockwise-duotone" />重试
            </button>
          </div>
          <FeedbackEmptyState
            v-else
            icon="i-ph-chart-line-duotone"
            title="运行回测后显示"
          >
            <template #hint>
              选择策略，调整参数，点击「运行回测」
            </template>
          </FeedbackEmptyState>
        </section>
      </div>
      </Pane>
    </LayoutSplitPane>
  </div>
</template>
