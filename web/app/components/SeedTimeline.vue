<script setup lang="ts">
// SeedTimeline: WS驱动的三步进度 + ETF方块网格
// 依据: 迭代/v3/README.md Phase 3 §SeedTimeline
import { computed } from '#imports'

interface Props {
  /** Current step identifier from WS */
  step: string
  /** Number of ETFs processed so far */
  current: number
  /** Total number of ETFs to process */
  total: number
  /** Total ETF count for grid display */
  etfCount?: number
}

const props = withDefaults(defineProps<Props>(), {
  etfCount: 30,
})

interface StepDef {
  key: string
  label: string
}

const stepDefs: StepDef[] = [
  { key: '交易日历', label: '交易日历' },
  { key: 'ETF元数据', label: 'ETF 元数据' },
  { key: '历史数据', label: '历史数据' },
]

/** Map step name to index. Step 3 is the data download phase with ETF grid. */
function stepIndex(stepName: string): number {
  const idx = stepDefs.findIndex(s => stepName.includes(s.key))
  return idx >= 0 ? idx : -1
}

const activeStepIdx = computed(() => stepIndex(props.step))
const showGrid = computed(() => activeStepIdx.value === 2)

/** Generate ETF block statuses: done < current, fetching = current, pending > current */
const etfBlocks = computed(() => {
  const blocks: Array<{ index: number; status: 'done' | 'fetching' | 'pending' }> = []
  for (let i = 0; i < props.etfCount; i++) {
    let status: 'done' | 'fetching' | 'pending'
    if (i < props.current) status = 'done'
    else if (i === props.current) status = 'fetching'
    else status = 'pending'
    blocks.push({ index: i, status })
  }
  return blocks
})
</script>

<template>
  <div class="flex gap-6 w-full max-w-2xl">
    <!-- 左侧: 三步竖线 + 圆点 -->
    <div class="flex flex-col gap-6 shrink-0" style="width: 120px">
      <div
        v-for="(s, i) in stepDefs"
        :key="s.key"
        class="flex items-center gap-2"
      >
        <!-- 状态圆点 -->
        <div class="relative flex items-center justify-center w-5 h-5 shrink-0">
          <!-- 竖线连接线 -->
          <div
            v-if="i < stepDefs.length - 1"
            class="absolute top-full w-0.5 h-6 bg-hover"
            :class="i < activeStepIdx ? 'bg-primary-400' : ''"
          />
          <!-- 圆点 -->
          <span
            v-if="i < activeStepIdx"
            class="i-ph-check-circle-fill text-sm color-primary-400"
          />
          <span
            v-else-if="i === activeStepIdx"
            class="i-ph-circle-notch-duotone text-sm color-active animate-spin"
          />
          <span
            v-else
            class="i-ph-circle text-sm op-mute"
          />
        </div>
        <span
          class="text-xs"
          :class="i <= activeStepIdx ? 'color-base' : 'op-mute'"
        >
          {{ s.label }}
        </span>
      </div>
    </div>

    <!-- 右侧: 内容区（步骤3展开 ETF 网格） -->
    <div class="flex-1 min-w-0">
      <!-- 步骤3: ETF 网格 -->
      <div v-if="showGrid" class="flex flex-col gap-2">
        <p class="text-xs op-fade font-mono tabular-nums">
          {{ current }} / {{ total }}
        </p>
        <div class="grid grid-cols-6 gap-1">
          <div
            v-for="block in etfBlocks"
            :key="block.index"
            class="aspect-square rounded-sm border transition-colors duration-300 flex items-center justify-center"
            :class="{
              'border-primary-400/30 bg-primary-400/15': block.status === 'done',
              'border-primary-400 bg-primary-400/10 animate-pulse': block.status === 'fetching',
              'border-pending bg-transparent': block.status === 'pending',
            }"
          >
            <span
              v-if="block.status === 'done'"
              class="i-ph-check-fill text-xs color-primary-400"
            />
            <span
              v-else-if="block.status === 'fetching'"
              class="text-micro font-mono tabular-nums color-active"
            >
              {{ block.index + 1 }}
            </span>
          </div>
        </div>
      </div>
      <!-- 步骤1-2: 无额外内容，仅状态指示 -->
      <p v-else class="text-xs op-fade">
        {{ activeStepIdx === 0 ? '检查交易日历...'
          : activeStepIdx === 1 ? '获取 ETF 元数据...'
          : '' }}
      </p>
    </div>
  </div>
</template>
