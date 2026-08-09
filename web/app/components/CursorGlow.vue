<script setup lang="ts">
// @env browser
// 光标光晕 - CSS radial-gradient 跟随鼠标
// Dashboard + Strategy 页启用
import { shallowRef, onMounted, onUnmounted } from '#imports'

const glowStyle = shallowRef<Record<string, string>>({ display: 'none' })
let rafId: number | null = null
let targetX = -500
let targetY = -500
let currentX = -500
let currentY = -500

function onMouseMove(e: MouseEvent) {
  targetX = e.clientX
  targetY = e.clientY
}

function updateGlow() {
  currentX += (targetX - currentX) * 0.05
  currentY += (targetY - currentY) * 0.05

  glowStyle.value = {
    display: 'block',
    left: `${currentX}px`,
    top: `${currentY}px`,
  }

  rafId = requestAnimationFrame(updateGlow)
}

onMounted(() => {
  window.addEventListener('mousemove', onMouseMove)
  rafId = requestAnimationFrame(updateGlow)
})

onUnmounted(() => {
  window.removeEventListener('mousemove', onMouseMove)
  if (rafId !== null) cancelAnimationFrame(rafId)
})
</script>

<template>
  <div
    class="fixed z-glow pointer-events-none"
    style="width: 400px; height: 400px; transform: translate(-50%, -50%)"
    :style="glowStyle"
  >
    <div
      class="w-full h-full rounded-full"
      style="background: radial-gradient(circle, rgba(73,131,62,0.10) 0%, rgba(73,131,62,0.04) 35%, transparent 70%)"
    />
  </div>
</template>
