<script setup lang="ts">
interface Props {
  type?: 'table' | 'card' | 'chart'
  rows?: number
}

withDefaults(defineProps<Props>(), {
  type: 'table',
  rows: 5,
})
</script>

<template>
  <div class="animate-pulse">
    <!-- Table skeleton -->
    <div v-if="type === 'table'" class="flex flex-col gap-1">
      <div
        v-for="i in rows"
        :key="i"
        class="h-6 bg-#8881 rounded"
        :style="{ width: `${85 - (i - 1) * 5}%` }"
      />
    </div>

    <!-- Card skeleton -->
    <div v-else-if="type === 'card'" class="grid grid-cols-3 gap-4">
      <div v-for="i in rows" :key="i" class="p-4 border border-base rounded">
        <div class="h-4 bg-#8881 rounded w-2/3 mb-2" />
        <div class="h-6 bg-#8881 rounded w-1/2" />
      </div>
    </div>

    <!-- Chart skeleton -->
    <div v-else-if="type === 'chart'" class="border border-base rounded p-4">
      <div class="h-48 bg-#8881 rounded" />
    </div>
  </div>
</template>
