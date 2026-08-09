<script setup lang="ts">
import { computed, shallowRef, onMounted } from '#imports'
import { useETFData } from '../composables/useETFData'

interface Props {
  modelValue: string | null
}

defineProps<Props>()

interface Emits {
  (e: 'update:modelValue', val: string): void
  (e: 'select', etf: any): void
}

const emit = defineEmits<Emits>()

const { etfs, fetchAll } = useETFData()
const search = shallowRef('')

onMounted(() => {
  fetchAll()
})

const filtered = computed(() => {
  if (!search.value) return etfs.value
  const q = search.value.toLowerCase()
  return etfs.value.filter(e =>
    e.code.toLowerCase().includes(q) || e.name.toLowerCase().includes(q),
  )
})
</script>

<template>
  <div class="flex flex-col gap-2">
    <input
      v-model="search"
      type="text"
      placeholder="搜索 ETF 代码或名称..."
      class="px-2 py-1 text-xs rounded border border-base bg-secondary color-base placeholder:op-mute outline-none focus:border-active transition-colors"
    >
    <div class="grid grid-cols-1 max-h-[300px] overflow-y-auto">
      <button
        v-for="etf in filtered"
        :key="etf.code"
        class="flex items-center gap-2 px-2 py-1 text-xs text-left rounded hover:bg-active transition-colors min-h-[28px]"
        :class="modelValue === etf.code ? 'bg-active color-active' : 'op-fade hover:op100'"
        @click="emit('update:modelValue', etf.code); emit('select', etf)"
      >
        <span class="font-mono shrink-0 w-[90px] truncate" :title="etf.code">{{ etf.code }}</span>
        <span class="truncate">{{ etf.name }}</span>
        <span class="text-micro px-1 py-px rounded border border-base op-mute uppercase tracking-wide ml-auto shrink-0">
          {{ etf.type }}
        </span>
      </button>
    </div>
  </div>
</template>
