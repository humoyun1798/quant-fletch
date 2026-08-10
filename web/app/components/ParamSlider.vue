<script setup lang="ts">
interface Props {
  label: string
  description?: string
  min: number
  max: number
  step?: number
  modelValue: number
}

withDefaults(defineProps<Props>(), {
  step: 1,
  description: '',
})

interface Emits {
  (e: 'update:modelValue', val: number): void
}

const emit = defineEmits<Emits>()

function onInput(e: Event) {
  const val = Number((e.target as HTMLInputElement).value)
  emit('update:modelValue', val)
}
</script>

<template>
  <div class="flex flex-col gap-1">
    <div class="flex items-center justify-between">
      <label class="text-xs color-base">{{ label }}</label>
      <span class="font-mono tabular-nums text-xs op-fade">{{ modelValue }}</span>
    </div>
    <div class="relative">
      <input
        type="range"
        :min="min"
        :max="max"
        :step="step"
        :value="modelValue"
        class="w-full h-1.5 rounded appearance-none bg-active cursor-pointer accent-primary"
        @input="onInput"
      >
    </div>
    <p v-if="description" class="text-micro op-mute">{{ description }}</p>
  </div>
</template>
