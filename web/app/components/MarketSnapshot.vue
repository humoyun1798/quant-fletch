<script setup lang="ts">
import { shallowRef, onMounted, watch } from '#imports'
import { useETFData } from '../composables/useETFData'
import { useMotion } from '../composables/useMotion'
import LoadingSkeleton from './LoadingSkeleton.vue'
import ErrorAlert from './ErrorAlert.vue'

const { etfs, loading, error, fetchAll } = useETFData()
const { staggerList, safeGsap } = useMotion()
const data = shallowRef<any[]>([])
const gridRef = shallowRef<HTMLElement>()

onMounted(async () => {
  await fetchAll()
  data.value = etfs.value
})

// 数据加载完成后 stagger 入场
watch(data, (val) => {
  if (!val || val.length === 0) return
  safeGsap(() => {
    if (gridRef.value) {
      staggerList(gridRef.value.querySelectorAll('.etf-card'))
    }
    return undefined
  })
})

// A 股涨跌色
function changeClass(val: number) {
  if (val > 0) return 'color-#EF4444'
  if (val < 0) return 'color-#22C45D'
  return 'op-fade'
}
</script>

<template>
  <section class="p-3 border-b border-base">
    <div class="flex items-center gap-2 mb-2">
      <h2 class="text-sm font-medium color-base">Market Snapshot</h2>
      <span class="text-micro op-mute font-mono tabular-nums">
        {{ data.length }} ETFs
      </span>
    </div>

    <LoadingSkeleton v-if="loading" :rows="3" type="table" />
    <ErrorAlert v-else-if="error" :message="error" @retry="fetchAll()" />

    <div v-else ref="gridRef" class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
      <div
        v-for="etf in data.slice(0, 12)"
        :key="etf.code"
        class="etf-card px-2 py-1.5 border border-base rounded text-xs"
      >
        <div class="flex items-center justify-between mb-0.5">
          <span class="font-mono op-fade truncate" :title="etf.code">
            {{ etf.code }}
          </span>
          <span class="text-micro px-1 py-px rounded border op-mute uppercase tracking-wide">
            {{ etf.type }}
          </span>
        </div>
        <p class="truncate text-xs">{{ etf.name }}</p>
        <div class="flex items-baseline gap-1.5 mt-1">
          <span class="font-mono tabular-nums text-sm">
            {{ etf.latest_close }}
          </span>
          <span class="font-mono tabular-nums text-micro" :class="changeClass(etf.change_pct)">
            {{ etf.change_pct > 0 ? '+' : '' }}{{ etf.change_pct.toFixed(2) }}%
          </span>
        </div>
      </div>
    </div>
  </section>
</template>
