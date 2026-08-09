<script setup lang="ts">
// Lightweight Charts 占位, 当回测有数据时渲染净值曲线
// 用法: <EquityCurveChart :data="result.equity_curve" />
import { shallowRef, watch, onMounted, onUnmounted } from '#imports'

interface Props {
  data: Array<{ date: string, equity: number, benchmark: number }>
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  height: 320,
})

interface Emits {
  (e: 'ready'): void
}

defineEmits<Emits>()

const container = shallowRef<HTMLDivElement>()

onMounted(() => {
  // Lightweight Charts 初始化, 当引入 createChart 后实现
})

onUnmounted(() => {
  // cleanup chart instance
})
</script>

<template>
  <div class="border border-base rounded overflow-hidden">
    <div v-if="data.length === 0" class="flex flex-col items-center justify-center gap-2" :style="{ height: `${height}px` }">
      <span class="i-ph-chart-line-duotone text-2xl op-mute" />
      <p class="text-xs op-fade">运行回测后显示净值曲线</p>
    </div>
    <div
      v-else
      ref="container"
      :style="{ height: `${height}px` }"
      class="w-full"
    />
  </div>
</template>
