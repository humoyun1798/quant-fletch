<script setup lang="ts">
import TopNav from '../components/TopNav.vue'
import TabBar from '../components/TabBar.vue'
import ParticleField from '../components/ParticleField.vue'
</script>

<template>
  <div class="app-shell">
    <TopNav />
    <TabBar />
    <ParticleField />
    <slot />
  </div>
</template>
