<script setup lang="ts">
import { useRoute } from '#imports'

const tabs = [
  { label: 'Dashboard', to: '/dashboard', icon: 'i-ph-gauge-duotone' },
  { label: 'Strategy', to: '/strategy', icon: 'i-ph-brain-duotone' },
  { label: 'Signals', to: '/signals', icon: 'i-ph-arrow-left-right-duotone' },
  { label: 'Data', to: '/data-browser', icon: 'i-ph-table-duotone' },
]

const route = useRoute()
</script>

<template>
  <nav class="h-nav flex items-center gap-1 px-3 border-b border-base bg-secondary shrink-0">
    <span class="mr-2 font-mono text-sm font-medium color-active tracking-wide">
      Rotor
    </span>
    <button
      v-for="tab in tabs"
      :key="tab.to"
      class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded transition-colors duration-150 min-w-[40px] min-h-[28px]"
      :class="route.path === tab.to ? 'bg-active color-active' : 'op-fade hover:op100 hover:bg-active'"
      @click="$router.push(tab.to)"
    >
      <span :class="tab.icon" class="text-sm" />
      {{ tab.label }}
    </button>
    <a
      href="/setup"
      class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded ml-auto transition-colors duration-150 min-w-[40px] min-h-[28px]"
      :class="route.path === '/setup' ? 'bg-active color-active' : 'op-fade hover:op100 hover:bg-active'"
    >
      <span class="i-ph-gear-duotone text-sm" />
      Setup
    </a>
  </nav>
</template>
