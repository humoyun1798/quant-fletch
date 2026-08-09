<script setup lang="ts">
import { shallowRef, watch, onMounted } from '#imports'
import { useStrategy } from '../composables/useStrategy'
import { useBacktest } from '../composables/useBacktest'
import { useMotion } from '../composables/useMotion'
import type { ParamDef } from '../types/strategy'
import type { BacktestConfig } from '../types/backtest'
import StrategyCardList from '../components/StrategyCardList.vue'
import ParamSelect from '../components/ParamSelect.vue'
import ParamSlider from '../components/ParamSlider.vue'
import BacktestTrigger from '../components/BacktestTrigger.vue'
import EquityCurveChart from '../components/EquityCurveChart.vue'
import MetricsRow from '../components/MetricsRow.vue'
import RebalanceHistory from '../components/RebalanceHistory.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import EmptyState from '../components/EmptyState.vue'

const { strategies, selected, params, fetchAll, selectStrategy } = useStrategy()
const backtest = useBacktest()
const { staggerList } = useMotion()

const selectedMeta = shallowRef<any | null>(null)

onMounted(async () => {
  await fetchAll()
  staggerList('.strategy-grid > *')
})

watch(selected, (name) => {
  if (name) {
    selectedMeta.value = strategies.value.find(s => s.name === name) ?? null
  }
})

function isSliderParam(p: ParamDef): boolean {
  return (p.type === 'int' || p.type === 'float') && p.min !== undefined && p.max !== undefined
}

function startBacktest() {
  if (!selected.value) return
  const config: BacktestConfig = {
    strategy: selected.value,
    params: { ...params.value },
    start_date: '2020-01-01',
    end_date: '2025-12-31',
    benchmark: '510300.SH',
  }
  backtest.run(config)
}
</script>

<template>
  <div class="strategy-grid flex-1 overflow-y-auto scroll-touch">
    <StrategyCardList />

    <section v-if="selected" class="p-3 border-b border-base">
      <div class="flex items-center gap-2 mb-2">
        <h2 class="text-sm font-medium color-base">Parameters</h2>
        <span class="font-mono text-xs color-active">{{ selected }}</span>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <template v-for="p in selectedMeta?.params ?? []" :key="p.name">
          <ParamSelect
            v-if="p.type === 'choice' && p.choices"
            :label="p.name"
            :choices="p.choices"
            :model-value="String(params[p.name] ?? p.default)"
            @update:model-value="(v: string) => params = { ...params, [p.name]: v }"
          />
          <ParamSlider
            v-else-if="isSliderParam(p)"
            :label="p.name"
            :description="p.description"
            :min="p.min!"
            :max="p.max!"
            :model-value="Number(params[p.name] ?? p.default)"
            @update:model-value="(v: number) => params = { ...params, [p.name]: v }"
          />
        </template>
      </div>
    </section>

    <section v-if="selected" class="p-3 border-b border-base">
      <BacktestTrigger
        :status="backtest.status.value"
        :progress="backtest.progress.value"
        :disabled="!selected"
        @run="startBacktest"
      />
    </section>

    <template v-if="backtest.result.value">
      <EquityCurveChart
        :data="backtest.result.value.equity_curve"
        @ready="staggerList('.metrics-row > *')"
      />
      <div class="metrics-row">
        <MetricsRow :metrics="backtest.result.value.metrics" />
      </div>
      <RebalanceHistory :signals="backtest.result.value.signals" />
    </template>

    <section v-else-if="backtest.status.value === 'completed'" class="p-3">
      <ErrorAlert
        v-if="backtest.error.value"
        :message="backtest.error.value"
        @retry="startBacktest()"
      />
      <EmptyState
        v-else
        icon="i-ph-chart-line-duotone"
        title="运行回测后显示"
        description="选择策略，调整参数，点击 Run Backtest"
      />
    </section>
  </div>
</template>
