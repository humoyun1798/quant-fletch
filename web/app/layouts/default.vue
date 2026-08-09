<script setup lang="ts">
import TopNav from '../components/TopNav.vue'
import TabBar from '../components/TabBar.vue'
</script>

<template>
  <div class="app-shell">
    <TopNav />
    <TabBar />
    <slot />
  </div>
</template>
