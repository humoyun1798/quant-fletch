<script setup lang="ts">
interface Props {
  label: string
  choices: string[]
  modelValue: string
}

defineProps<Props>()

interface Emits {
  (e: 'update:modelValue', val: string): void
}

defineEmits<Emits>()
</script>

<template>
  <div class="flex flex-col gap-1">
    <label class="text-xs color-base">{{ label }}</label>
    <select
      :value="modelValue"
      class="px-2 py-1 text-xs rounded border border-base bg-secondary color-base cursor-pointer min-h-[28px]"
      @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
    >
      <option v-for="c in choices" :key="c" :value="c">{{ c }}</option>
    </select>
  </div>
</template>
