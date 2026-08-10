<script setup lang="ts">
import { $fetch } from '#build/fetch.mjs'
import { shallowRef, computed, onMounted, onUnmounted } from '#imports'
import ActionButton from '@antfu/design/components/Action/ActionButton.vue'
import SeedHero from '../components/SeedHero.vue'
import SeedTimeline from '../components/SeedTimeline.vue'
import SeedProgressRing from '../components/SeedProgressRing.vue'
import SeedResult from '../components/SeedResult.vue'
import { WS_BASE } from '../config/api'

interface SeedProgress {
  step: string
  current?: number
  total?: number
  status?: string
  message?: string
}

interface FailedEtf {
  code: string
  name?: string
  error?: string
}

const status = shallowRef<string>('loading')
const seedProgress = shallowRef<SeedProgress | null>(null)
const failedEtfs = shallowRef<FailedEtf[]>([])
let ws: WebSocket | null = null

const current = computed(() => seedProgress.value?.current ?? 0)
const total = computed(() => seedProgress.value?.total ?? 30)
const currentStep = computed(() => seedProgress.value?.step ?? '')

async function checkStatus() {
  try {
    const res = await $fetch<{ data: { status: string, progress?: Record<string, unknown> } }>('/api/v1/system/status')
    const d = res.data
    status.value = d.status
    if (d.progress) {
      seedProgress.value = d.progress as SeedProgress
    }
  }
  catch {
    status.value = 'error'
  }
}

function connectSeedWs(wsUrl: string) {
  if (ws) { ws.close(); ws = null }

  ws = new WebSocket(`${WS_BASE}${wsUrl}`)
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data) as SeedProgress & { failed_etfs?: FailedEtf[] }
    seedProgress.value = { ...seedProgress.value, ...msg }

    if (msg.failed_etfs) {
      failedEtfs.value = msg.failed_etfs
    }

    if (msg.step === 'complete') {
      ws?.close()
      ws = null
      checkStatus()
    }
    else if (msg.step === 'error') {
      ws?.close()
      ws = null
      status.value = 'error'
    }
  }
  ws.onerror = () => {
    ws?.close()
    ws = null
  }
}

async function triggerSeed(mode: string) {
  status.value = 'seeding'
  failedEtfs.value = []
  seedProgress.value = null
  try {
    const res = await $fetch<{ data: { ws_url: string } }>('/api/v1/system/seed', {
      method: 'POST',
      body: { mode },
    })
    connectSeedWs(res.data.ws_url)
  }
  catch {
    status.value = 'error'
  }
}

onMounted(() => {
  checkStatus()
})

onUnmounted(() => {
  if (ws) { ws.close(); ws = null }
})
</script>

<template>
  <div class="flex-1 overflow-y-auto scroll-touch flex flex-col items-center justify-center p-6">
    <div class="max-w-2xl w-full flex flex-col items-center gap-6">
      <!-- 加载中 -->
      <div v-if="status === 'loading'" class="flex items-center gap-2 text-sm op-fade">
        <span class="i-ph-circle-notch-duotone animate-spin" />
        检查系统状态...
      </div>

      <!-- 未种子: 显示开始按钮 -->
      <div v-else-if="status === 'not_seeded'" class="flex flex-col items-center gap-4">
        <span class="i-ph-rocket-launch-duotone text-4xl color-active" />
        <p class="text-sm op-fade text-center max-w-md">
          没有找到数据。运行种子流程以获取 ETF 历史数据（需要网络访问 AkShare）。
        </p>
        <ActionButton variant="primary" @click="triggerSeed('full')">
          <span class="i-ph-seedling-duotone" />开始初始化
        </ActionButton>
      </div>

      <!-- 已就绪: 显示重新种子按钮 -->
      <div v-else-if="status === 'ready' && !seedProgress" class="flex flex-col items-center gap-4">
        <SeedResult
          status="ready"
          :total-count="30"
          :success-count="30"
        />
      </div>

      <!-- 种子进行中 -->
      <template v-else-if="status === 'seeding'">
        <SeedHero :running="true" />
        <div class="flex flex-col md:flex-row items-center gap-8 w-full justify-center">
          <SeedTimeline
            :step="currentStep"
            :current="current"
            :total="total"
            :etf-count="total"
          />
          <SeedProgressRing
            :current="current"
            :total="total"
          />
        </div>
      </template>

      <!-- 错误 / 完成覆盖 -->
      <SeedResult
        v-else-if="status === 'error' || status === 'ready'"
        :status="status === 'ready' ? 'ready' : 'error'"
        :total-count="total"
        :success-count="current"
        :failed-etfs="failedEtfs"
        :error-message="seedProgress?.message"
        @retry="triggerSeed"
      />

      <!-- 未知状态 (fallback) -->
      <div v-else class="text-sm op-fade">
        状态: {{ status }}
      </div>
    </div>
  </div>
</template>
