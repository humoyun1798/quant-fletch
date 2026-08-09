<script setup lang="ts">
import { shallowRef, useNuxtApp } from '#imports'
import { useMotion } from '../composables/useMotion'
import StatusBadge from './StatusBadge.vue'

interface Props {
  status: string
  progress: number
  disabled: boolean
}

defineProps<Props>()

interface Emits {
  (e: 'run'): void
}

const emit = defineEmits<Emits>()
const { $gsap } = useNuxtApp()
const gsap = $gsap!
const { safeGsap } = useMotion()
const btnRef = shallowRef<HTMLElement>()

function onPointerDown() {
  safeGsap(() => {
    if (btnRef.value) {
      gsap.to(btnRef.value, { scale: 0.96, duration: 0.08, ease: 'power1.in' })
    }
    return undefined
  })
}

function onPointerUp() {
  safeGsap(() => {
    if (btnRef.value) {
      gsap.to(btnRef.value, { scale: 1, duration: 0.15, ease: 'back.out(1.7)' })
    }
    return undefined
  })
}

function onClick() {
  emit('run')
}
</script>

<template>
  <div class="flex items-center gap-3">
    <button
      ref="btnRef"
      class="btn-action"
      :disabled="disabled || status === 'running'"
      @pointerdown="onPointerDown"
      @pointerup="onPointerUp"
      @pointerleave="onPointerUp"
      @click="onClick"
    >
      <span
        class="text-sm"
        :class="status === 'running' ? 'i-ph-circle-notch-duotone animate-spin' : 'i-ph-play-circle-duotone'"
      />
      {{ status === 'running' ? `Running ${Math.round(progress * 100)}%` : 'Run Backtest' }}
    </button>

    <StatusBadge :status="status === 'running' ? 'running' : status === 'completed' ? 'completed' : status === 'failed' ? 'failed' : 'idle'" />
  </div>
</template>
