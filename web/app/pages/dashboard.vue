<script setup lang="ts">
import { onMounted } from '#imports'
import { useMotion } from '../composables/useMotion'
import MarketSnapshot from '../components/MarketSnapshot.vue'
import ETFHeatmap from '../components/ETFHeatmap.vue'
import CurrentPositions from '../components/CurrentPositions.vue'

const { staggerList } = useMotion()

onMounted(() => {
  staggerList('.dashboard-grid > *')
})
</script>

<template>
  <div class="dashboard-grid flex-1 overflow-y-auto scroll-touch">
    <MarketSnapshot />
    <ETFHeatmap />
    <CurrentPositions />
  </div>
</template>
