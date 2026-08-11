<script setup lang="ts">
import { useDark, useToggle } from '@vueuse/core'
import ActionIconButton from '@antfu/design/components/Action/ActionIconButton.vue'

const isDark = useDark()
const toggleDark = useToggle(isDark)
</script>

<template>
  <header class="h-nav flex items-center justify-between px-4 bg-base border-b border-base shrink-0 z-nav">
    <div class="flex items-center gap-2">
      <span class="i-ph-chart-bar-duotone text-lg color-active" />
      <span class="font-medium text-sm tracking-wide color-base">
        Quant-Fletch
      </span>
    </div>
    <div class="flex items-center gap-1">
      <ClientOnly>
        <ActionIconButton
          :icon="isDark ? 'i-ph-sun' : 'i-ph-moon'"
          :label="isDark ? '亮色' : '暗色'"
          :tooltip="isDark ? '切换亮色' : '切换暗色'"
          @click="toggleDark()"
        />
        <template #fallback>
          <ActionIconButton
            icon="i-ph-moon-duotone"
            label="主题"
            tooltip="切换主题"
          />
        </template>
      </ClientOnly>
      <ActionIconButton
        href="https://github.com/AbelTami/quant-fletch"
        icon="i-ph-github-logo-duotone"
        label="GitHub"
        tooltip="GitHub"
      />
    </div>
  </header>
</template>
