<script setup lang="ts">
import { shallowRef, onMounted, onUnmounted } from '#imports'
import ErrorAlert from '../components/ErrorAlert.vue'

interface SeedProgress {
  step: string
  current?: number
  total?: number
  status?: string
  message?: string
}

const status = shallowRef<string>('loading')
const seedProgress = shallowRef<SeedProgress | null>(null)
let ws: WebSocket | null = null

async function checkStatus() {
  try {
    const res = await $fetch<{ data: any }>('/api/v1/system/status')
    const d = res.data
    status.value = d.status
    if (d.progress) {
      seedProgress.value = d.progress
    }
  }
  catch {
    status.value = 'error'
  }
}

function connectSeedWs(wsUrl: string) {
  if (ws) { ws.close(); ws = null }

  ws = new WebSocket(`ws://localhost:8000${wsUrl}`)
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    seedProgress.value = { ...seedProgress.value, ...msg }

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

function progressPct(): number {
  if (!seedProgress.value?.total) return 0
  return ((seedProgress.value.current ?? 0) / seedProgress.value.total) * 100
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
    <div class="max-w-md w-full flex flex-col items-center gap-4">
      <span class="i-ph-rocket-launch-duotone text-4xl color-active" />
      <h1 class="text-lg font-medium color-base">System Setup</h1>

      <div v-if="status === 'loading'" class="flex items-center gap-2 text-sm op-fade">
        <span class="i-ph-circle-notch-duotone animate-spin" />
        Checking system status...
      </div>

      <div v-else-if="status === 'not_seeded'" class="flex flex-col items-center gap-3 w-full">
        <p class="text-sm op-fade text-center">
          No data found. Run the seed process to fetch ETF historical data (requires network access to AkShare).
        </p>
        <button class="btn-action" @click="triggerSeed('full')">
          <span class="i-ph-seedling-duotone" />
          Start Seed (Full)
        </button>
      </div>

      <div v-else-if="status === 'ready'" class="flex flex-col items-center gap-3 w-full">
        <div class="flex items-center gap-2">
          <span class="i-ph-check-circle-duotone text-green-500" />
          <span class="text-sm color-base">System Ready</span>
        </div>
        <button class="btn-action" @click="triggerSeed('full')">
          <span class="i-ph-arrow-clockwise-duotone" />
          Re-run Seed
        </button>
      </div>

      <div v-else-if="status === 'seeding'" class="flex flex-col items-center gap-3 w-full">
        <div class="flex items-center gap-2 text-sm">
          <span class="i-ph-circle-notch-duotone animate-spin color-active" />
          Seeding in progress...
        </div>
        <div class="w-full bg-#8882 rounded h-1.5 overflow-hidden">
          <div
            class="h-full bg-primary rounded transition-width duration-300"
            :style="{ width: `${progressPct()}%` }"
          />
        </div>
        <p class="text-xs op-fade font-mono">
          {{ seedProgress?.step ?? 'initializing' }}
          <template v-if="seedProgress?.current">
            ({{ seedProgress.current }}/{{ seedProgress.total }})
          </template>
        </p>
      </div>

      <div v-else-if="status === 'error'" class="flex flex-col items-center gap-3 w-full">
        <ErrorAlert
          message="System check failed. Ensure API server and database are running."
          @retry="checkStatus"
        />
      </div>
    </div>
  </div>
</template>
