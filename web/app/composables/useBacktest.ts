// @env browser
// 回测执行 — 模块级单例，strategy 页和 signals 页共享回测状态
// 依据: 05-回测引擎.md §前端集成 + 07-前端设计.md §Composable 设计
import { $fetch } from '#build/fetch.mjs'
import { ref, shallowRef } from '#imports'
import type { BacktestResult, BacktestConfig } from '../types/backtest'
import { WS_BASE } from '../config/api'

const status = shallowRef<'idle' | 'queued' | 'running' | 'completed' | 'failed'>('idle')
const progress = ref(0)
const currentStep = shallowRef('')
const currentDate = shallowRef('')
const result = shallowRef<BacktestResult | null>(null)
const error = shallowRef<string | null>(null)

export function useBacktest() {
  async function run(config: BacktestConfig) {
    status.value = 'queued'
    progress.value = 0
    currentStep.value = ''
    currentDate.value = ''
    error.value = null

    try {
      const res = await $fetch<{ data: { run_id: string, status: string, ws_url: string } }>('/api/v1/backtest', {
        method: 'POST',
        body: config,
      })

      const { run_id, ws_url } = res.data
      status.value = 'running'

      // WebSocket 直连 API 服务器（不走 Nitro 代理）
      const ws = new WebSocket(`${WS_BASE}${ws_url}`)

      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        progress.value = msg.progress ?? progress.value
        currentStep.value = msg.step ?? currentStep.value
        currentDate.value = msg.current_date ?? currentDate.value

        if (msg.step === 'completed') {
          ws.close()
          fetchResult(run_id)
        }
        else if (msg.step === 'failed') {
          ws.close()
          status.value = 'failed'
          error.value = msg.message ?? '回测执行失败'
        }
      }

      ws.onerror = () => {
        ws.close()
        status.value = 'failed'
        error.value = 'WebSocket 连接失败'
      }
    }
    catch (e: unknown) {
      status.value = 'failed'
      const msg = e instanceof Error ? e.message : '回测启动失败'
      // API errors may come with structured data
      const apiError = (e as { data?: { error?: { message?: string } } }).data?.error?.message
      error.value = apiError ?? msg
    }
  }

  async function fetchResult(runId: string) {
    try {
      const res = await $fetch<{ data: BacktestResult }>(`/api/v1/backtest/${runId}`)
      result.value = res.data
      status.value = res.data.status
    }
    catch (e: unknown) {
      status.value = 'failed'
      error.value = e instanceof Error ? e.message : '获取回测结果失败'
    }
  }

  return { status, progress, currentStep, currentDate, result, error, run }
}
