<script setup lang="ts">
import { shallowRef, onMounted } from '#imports'
import { useETFData } from '../composables/useETFData'
import { useMotion } from '../composables/useMotion'
import type { Bar, BarPeriod } from '../types/etf'
import ETFPicker from '../components/ETFPicker.vue'
import KlineChart from '../components/KlineChart.vue'
import OHLCVTable from '../components/OHLCVTable.vue'

const { fetchBars } = useETFData()
const { staggerList } = useMotion()

const selectedCode = shallowRef<string | null>(null)
const barData = shallowRef<Bar[]>([])
const period = shallowRef<BarPeriod>('daily')

const periodOptions: { label: string; value: BarPeriod }[] = [
  { label: '日线', value: 'daily' },
  { label: '60m', value: '60m' },
  { label: '30m', value: '30m' },
  { label: '15m', value: '15m' },
  { label: '5m', value: '5m' },
  { label: '1m', value: '1m' },
]

onMounted(() => {
  staggerList('.data-grid > *')
})

async function fetchData() {
  if (!selectedCode.value) return
  const data = await fetchBars(selectedCode.value, period.value)
  if (data) barData.value = data
}

async function onSelect(etf: any) {
  selectedCode.value = etf.code
  await fetchData()
}

async function onPeriodChange(p: BarPeriod) {
  period.value = p
  await fetchData()
}
</script>

<template>
  <div class="data-grid flex-1 overflow-y-auto scroll-touch">
    <section class="p-3 border-b border-base">
      <h2 class="text-sm font-medium color-base mb-2">Data Browser</h2>
      <div class="flex items-center gap-1 mb-3">
        <button
          v-for="opt in periodOptions"
          :key="opt.value"
          class="px-2 py-0.5 text-xs rounded border transition-colors duration-150 font-mono tabular-nums min-w-[32px] min-h-[24px]"
          :class="period === opt.value ? 'border-active color-active bg-active' : 'border-base op-fade hover:op100 hover:bg-active'"
          @click="onPeriodChange(opt.value)"
        >
          {{ opt.label }}
        </button>
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-3">
        <ETFPicker :model-value="selectedCode" @select="onSelect" />
        <div>
          <KlineChart :data="barData" :period="period" />
          <OHLCVTable :data="barData" class="mt-3" />
        </div>
      </div>
    </section>
  </div>
</template>
