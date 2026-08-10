<script setup lang="ts">
import ActionIconButton from '@antfu/design/components/Action/ActionIconButton.vue'
</script>

<template>
  <header class="h-nav flex items-center justify-between px-4 bg-base border-b border-base shrink-0 z-top-nav">
    <div class="flex items-center gap-2">
      <span class="i-ph-chart-bar-duotone text-lg color-active" />
      <span class="font-medium text-sm tracking-wide color-base">
        Quant-Fletch
      </span>
    </div>
    <ActionIconButton
      href="https://github.com/AbelTami/quant-fletch"
      icon="i-ph-github-logo-duotone"
      label="GitHub"
      tooltip="GitHub"
    />
  </header>
</template>
