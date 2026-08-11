<script setup lang="ts">
import { shallowRef, computed, onMounted } from '#imports'
import { useETFData } from '../composables/useETFData'
import { useMotion } from '../composables/useMotion'
import FormCombobox from '@antfu/design/components/Form/FormCombobox.vue'
import type { ComboboxOption } from '@antfu/design/components/Form/FormCombobox.vue'
import LayoutDataTable from '@antfu/design/components/Layout/LayoutDataTable.vue'
import type { Column } from '@antfu/design/components/Layout/LayoutDataTable.vue'
import LayoutToolbar from '@antfu/design/components/Layout/LayoutToolbar.vue'
import LayoutSplitPane from '@antfu/design/components/Layout/LayoutSplitPane.vue'
import { Pane } from 'splitpanes'
import KlineChart from '../components/KlineChart.vue'

const { etfs, ohlcv, fetchOHLCV, fetchAll } = useETFData()
const { staggerList, safeGsap } = useMotion()

const selectedCode = shallowRef<string>('')
const loading = shallowRef(false)

const ohlcvColumns: Column[] = [
  { key: 'date', label: 'Date', width: '100px' },
  { key: 'open', label: 'Open', align: 'right', sortable: true },
  { key: 'high', label: 'High', align: 'right', sortable: true },
  { key: 'low', label: 'Low', align: 'right', sortable: true },
  { key: 'close', label: 'Close', align: 'right', sortable: true },
  { key: 'volume', label: 'Volume', align: 'right', sortable: true },
]

onMounted(() => {
  fetchAll()
})

const etfOptions = computed<ComboboxOption[]>(() =>
  etfs.value.map(e => ({
    value: e.code,
    label: `${e.code}  ${e.name}`,
  })),
)

function dateRange() {
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 365)
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  }
}

async function onSelect(code: string | undefined) {
  if (!code || code === selectedCode.value) return
  selectedCode.value = code
  loading.value = true
  const range = dateRange()
  await fetchOHLCV(code, range.start, range.end)
  loading.value = false
  safeGsap(() => {
    staggerList('.data-grid > *')
    return undefined
  })
}
</script>

<template>
  <div class="data-grid flex-1 overflow-y-auto scroll-touch flex flex-col">
    <LayoutToolbar>
      <template #start>
        <h2 class="text-sm font-medium color-base shrink-0">Data Browser</h2>
        <FormCombobox
          :options="etfOptions"
          :model-value="selectedCode"
          placeholder="搜索 ETF 代码或名称..."
          class="w-72"
          @update:model-value="onSelect"
        />
      </template>
    </LayoutToolbar>

    <LayoutSplitPane horizontal storage-key="data-browser-split" class="flex-1">
      <Pane :size="40" :min-size="20">
      <div class="min-h-[256px] h-full">
        <KlineChart :data="ohlcv" />
      </div>
      </Pane>
      <Pane :size="60" :min-size="20">
      <div class="min-h-[128px] h-full">
        <div v-if="ohlcv.length === 0" class="text-xs op-fade py-4 text-center">
          选择 ETF 查看数据
        </div>
        <LayoutDataTable
          v-else
          :columns="ohlcvColumns"
          :rows="ohlcv"
          manual-sort
          class="max-h-full overflow-auto"
        >
          <template #cell="{ column, value }">
            <span v-if="column.key === 'date'" class="font-mono tabular-nums">{{ String(value).slice(0, 10) }}</span>
            <span v-else-if="column.key === 'volume'" class="font-mono tabular-nums">{{ (value as number).toLocaleString() }}</span>
            <span v-else class="font-mono tabular-nums">{{ (value as number).toFixed(3) }}</span>
          </template>
        </LayoutDataTable>
      </div>
      </Pane>
    </LayoutSplitPane>
  </div>
</template>
