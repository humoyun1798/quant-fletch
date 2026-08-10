<script setup lang="ts">
import { shallowRef, computed, useNuxtApp } from '#imports'
import { useMotion } from '../composables/useMotion'
import DisplayBadge from '@antfu/design/components/Display/DisplayBadge.vue'

interface Props {
  status: string
  progress: number
  disabled: boolean
}

const props = defineProps<Props>()

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

const badgeText = computed(() => {
  const map: Record<string, string> = { running: '运行中', completed: '已完成', failed: '失败' }
  return map[props.status] || props.status
})

const badgeColor = computed(() => {
  const map: Record<string, string> = { running: 'blue', completed: 'green', failed: 'red' }
  return map[props.status] || false
})
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

    <DisplayBadge v-if="status !== 'idle'" :text="badgeText" variant="solid" :color="badgeColor" />
  </div>
</template>
