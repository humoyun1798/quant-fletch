<script setup lang="ts">
import '@unocss/reset/tailwind.css'
import '@antfu/design/styles.css'

import { useMotion } from './composables/useMotion'

const { pageEnter, pageLeave } = useMotion()
</script>

<template>
  <NuxtLayout>
    <NuxtPage v-slot="{ Component, route }">
      <Transition
        mode="out-in"
        @enter="pageEnter"
        @leave="pageLeave"
      >
        <!-- eslint-disable-next-line vue/no-template-shadow, unimport/auto-insert -->
        <component :is="Component" :key="route.path" />
      </Transition>
    </NuxtPage>
  </NuxtLayout>
</template>

<style>
.splitpanes__splitter::before {
  inset: -2px !important;
}
.splitpanes__pane {
  overflow: auto !important;
}
</style>
