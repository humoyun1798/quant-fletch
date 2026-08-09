<script setup lang="ts">
interface Props {
  status: 'queued' | 'running' | 'completed' | 'failed' | 'idle'
}

defineProps<Props>()

const iconMap: Record<string, string> = {
  queued: 'i-ph-hourglass-duotone',
  running: 'i-ph-circle-notch-duotone',
  completed: 'i-ph-check-circle-duotone',
  failed: 'i-ph-x-circle-duotone',
  idle: 'i-ph-pause-circle-duotone',
}

const colorMap: Record<string, string> = {
  queued: 'color-yellow-500 border-yellow-500/25',
  running: 'color-blue-500 border-blue-500/25',
  completed: 'color-green-500 border-green-500/25',
  failed: 'color-red-500 border-red-500/25',
  idle: 'op-fade',
}

const labelMap: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  idle: '空闲',
}
</script>

<template>
  <span
    class="inline-flex items-center gap-1 px-1.5 py-px rounded border text-micro uppercase tracking-wide font-mono"
    :class="colorMap[status]"
  >
    <span v-if="status === 'running'" class="i-ph-circle-notch-duotone animate-spin text-xs" />
    <span v-else :class="iconMap[status]" class="text-xs" />
    {{ labelMap[status] }}
  </span>
</template>
