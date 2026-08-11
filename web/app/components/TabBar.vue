<script setup lang="ts">
import { computed, useRoute, useRouter } from '#imports'
import LayoutTabs from '@antfu/design/components/Layout/LayoutTabs.vue'
import type { TabItem } from '@antfu/design/components/Layout/LayoutTabs.vue'

const tabs: TabItem[] = [
  { value: '/dashboard', label: '仪表盘', icon: 'i-ph-gauge-duotone' },
  { value: '/strategy', label: '策略工作室', icon: 'i-ph-brain-duotone' },
  { value: '/signals', label: '信号记录', icon: 'i-ph-arrows-left-right-duotone' },
  { value: '/data-browser', label: '数据浏览器', icon: 'i-ph-table-duotone' },
]

const route = useRoute()
const router = useRouter()

const activeTab = computed({
  get: () => route.path,
  set: (val: string) => router.push(val),
})
</script>

<template>
  <LayoutTabs v-model="activeTab" :tabs="tabs" />
</template>
