<script setup lang="ts">
import type { Bar } from '../types/etf'

interface Props {
  data: Bar[]
}

defineProps<Props>()
</script>

<template>
  <div>
    <div v-if="data.length === 0" class="text-xs op-fade py-4 text-center">
      选择 ETF 查看数据
    </div>
    <div v-else class="overflow-x-auto">
      <table class="w-full text-xs">
        <thead>
          <tr class="border-b border-base text-left op-fade text-micro uppercase tracking-wide">
            <th class="px-2 py-1 font-medium font-mono">Time</th>
            <th class="px-2 py-1 font-medium font-mono text-right">Open</th>
            <th class="px-2 py-1 font-medium font-mono text-right">High</th>
            <th class="px-2 py-1 font-medium font-mono text-right">Low</th>
            <th class="px-2 py-1 font-medium font-mono text-right">Close</th>
            <th class="px-2 py-1 font-medium font-mono text-right">Volume</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, idx) in data.slice(-50)"
            :key="idx"
            class="border-b border-base/50 hover:bg-active transition-colors duration-100"
          >
            <td class="px-2 py-0.5 font-mono tabular-nums max-w-[160px] truncate" :title="row.dt">{{ row.dt }}</td>
            <td class="px-2 py-0.5 font-mono tabular-nums text-right">{{ row.open.toFixed(3) }}</td>
            <td class="px-2 py-0.5 font-mono tabular-nums text-right">{{ row.high.toFixed(3) }}</td>
            <td class="px-2 py-0.5 font-mono tabular-nums text-right">{{ row.low.toFixed(3) }}</td>
            <td class="px-2 py-0.5 font-mono tabular-nums text-right">{{ row.close.toFixed(3) }}</td>
            <td class="px-2 py-0.5 font-mono tabular-nums text-right">{{ row.volume.toLocaleString() }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
