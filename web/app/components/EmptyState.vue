<script setup lang="ts">
interface Props {
  icon?: string
  title: string
  description?: string
  actionLabel?: string
}

withDefaults(defineProps<Props>(), {
  icon: 'i-ph-database-duotone',
  description: '',
  actionLabel: '',
})

interface Emits {
  (e: 'action'): void
}

defineEmits<Emits>()
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-3 py-12 px-4">
    <span v-if="icon" :class="icon" class="text-3xl op-mute" />
    <p class="text-lg font-medium color-base">
      {{ title }}
    </p>
    <p v-if="description" class="text-sm text-center max-w-80 op-fade">
      {{ description }}
    </p>
    <button
      v-if="actionLabel"
      class="btn-action mt-2"
      @click="$emit('action')"
    >
      {{ actionLabel }}
    </button>
  </div>
</template>
