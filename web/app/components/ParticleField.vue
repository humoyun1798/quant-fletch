<script setup lang="ts">
// @env browser
// 背景粒子场 - 暗色背景上稀疏微光点缓慢漂浮 (50-80 particles, canvas 60fps)
import { shallowRef, onMounted, onUnmounted, useNuxtApp } from '#imports'

const { $gsapLowPerf: lowPerf } = useNuxtApp() as { $gsapLowPerf: boolean }
const canvasRef = shallowRef<HTMLCanvasElement>()

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  alpha: number
  alphaTarget: number
}

let ctx: CanvasRenderingContext2D | null = null
let particles: Particle[] = []
let mouseX = -1000
let mouseY = -1000
let animationId: number | null = null
let width = 0
let height = 0

function createParticle(w: number, h: number): Particle {
  return {
    x: Math.random() * w,
    y: Math.random() * h,
    vx: (Math.random() - 0.5) * 0.3,
    vy: (Math.random() - 0.5) * 0.3,
    radius: 1 + Math.random() * 1.5,
    alpha: 0.15 + Math.random() * 0.15,
    alphaTarget: 0.15 + Math.random() * 0.15,
  }
}

function initParticles(count: number, w: number, h: number) {
  particles = Array.from({ length: count }, () => createParticle(w, h))
}

function draw() {
  if (!ctx || !canvasRef.value) return

  ctx.clearRect(0, 0, width, height)

  for (const p of particles) {
    // 缓慢漂移
    p.x += p.vx
    p.y += p.vy

    // 边界环绕
    if (p.x < -10) p.x = width + 10
    if (p.x > width + 10) p.x = -10
    if (p.y < -10) p.y = height + 10
    if (p.y > height + 10) p.y = -10

    // 鼠标吸引 (120px 半径)
    const dx = mouseX - p.x
    const dy = mouseY - p.y
    const dist = Math.sqrt(dx * dx + dy * dy)
    if (dist < 120 && dist > 0) {
      const force = (120 - dist) / 120 * 0.02
      p.vx += dx / dist * force
      p.vy += dy / dist * force
    }

    // 阻尼
    p.vx *= 0.998
    p.vy *= 0.998

    // alpha 呼吸
    const diff = p.alphaTarget - p.alpha
    p.alpha += diff * 0.01

    // 绘制
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(124,188,113,${p.alpha})`
    ctx.fill()
  }
}

function resize() {
  if (!canvasRef.value) return
  width = window.innerWidth
  height = window.innerHeight
  canvasRef.value.width = width * window.devicePixelRatio
  canvasRef.value.height = height * window.devicePixelRatio
  canvasRef.value.style.width = `${width}px`
  canvasRef.value.style.height = `${height}px`
  ctx = canvasRef.value.getContext('2d')
  if (ctx) ctx.scale(window.devicePixelRatio, window.devicePixelRatio)
}

function onMouseMove(e: MouseEvent) {
  mouseX = e.clientX
  mouseY = e.clientY
}

function tick() {
  draw()
  animationId = requestAnimationFrame(tick)
}

onMounted(() => {
  if (lowPerf) return // 低性能设备降级

  resize()
  initParticles(lowPerf ? 25 : 60, width, height)
  window.addEventListener('resize', resize)
  window.addEventListener('mousemove', onMouseMove)
  animationId = requestAnimationFrame(tick)
})

onUnmounted(() => {
  if (animationId !== null) {
    cancelAnimationFrame(animationId)
  }
  window.removeEventListener('resize', resize)
  window.removeEventListener('mousemove', onMouseMove)
})
</script>

<template>
  <canvas
    v-if="!lowPerf"
    ref="canvasRef"
    class="fixed inset-0 z-particle pointer-events-none"
    style="opacity: 0.6"
  />
</template>
