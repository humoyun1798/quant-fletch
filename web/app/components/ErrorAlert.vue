<script setup lang="ts">
interface Props {
  message: string
  retryLabel?: string
}

withDefaults(defineProps<Props>(), {
  retryLabel: '重试',
})

interface Emits {
  (e: 'retry'): void
}

defineEmits<Emits>()
</script>

<template>
  <div class="flex items-center gap-3 px-3 py-2 rounded border border-red-400/25 bg-red-50 dark:bg-red-950/20">
    <span class="i-ph-warning-duotone text-red-500 text-lg shrink-0" />
    <p class="text-sm color-base flex-1 min-w-0">{{ message }}</p>
    <button
      class="btn-action text-sm shrink-0"
      @click="$emit('retry')"
    >
      <span class="i-ph-arrow-clockwise-duotone" />
      {{ retryLabel }}
    </button>
  </div>
</template>
