<script setup lang="ts">
import { shallowRef, onMounted } from '#imports'
import { useStrategy } from '../composables/useStrategy'
import { useMotion } from '../composables/useMotion'
import FeedbackSkeleton from '@antfu/design/components/Feedback/FeedbackSkeleton.vue'

const { strategies, selected, fetchAll, selectStrategy } = useStrategy()
const { glowPulse, safeGsap } = useMotion()
const loading = shallowRef(false)
const cardRefs = shallowRef<Map<string, HTMLElement>>(new Map())

onMounted(async () => {
  loading.value = true
  await fetchAll()
  loading.value = false
})

function setCardRef(name: string, el: unknown) {
  if (el instanceof Element) cardRefs.value.set(name, el as HTMLElement)
}

function onSelect(name: string) {
  selectStrategy(name)
  // 选中时触发光脉冲
  safeGsap(() => {
    const card = cardRefs.value.get(name)
    if (card) {
      glowPulse(card)
    }
    return undefined
  })
}
</script>

<template>
  <section class="p-3 border-b border-base">
    <h2 class="text-sm font-medium color-base mb-2">Available Strategies</h2>

    <FeedbackSkeleton v-if="loading" variant="text" :lines="5" />

    <div v-else-if="strategies.length === 0" class="text-xs op-fade">
      暂无可用策略
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
      <button
        v-for="s in strategies"
        :key="s.name"
        :ref="(el: unknown) => setCardRef(s.name, el)"
        class="text-left px-3 py-2 border rounded transition-colors duration-150 min-h-[40px]"
        :class="selected === s.name ? 'border-active bg-active' : 'border-base hover:bg-active'"
        @click="onSelect(s.name)"
      >
        <div class="flex items-center gap-1.5 mb-1">
          <span class="text-xs font-medium color-base">{{ s.name }}</span>
          <span class="text-micro op-mute font-mono">v{{ s.version }}</span>
        </div>
        <p class="text-xs op-fade line-clamp-2">{{ s.description }}</p>
        <div class="flex flex-wrap gap-1 mt-1.5">
          <span
            v-for="tag in s.tags"
            :key="tag"
            class="px-1 py-px rounded border border-base text-micro uppercase tracking-wide op-fade"
          >
            {{ tag }}
          </span>
        </div>
      </button>
    </div>
  </section>
</template>
