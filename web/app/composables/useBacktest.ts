// @env browser
import { shallowRef } from '#imports'
import type { BacktestResult, BacktestConfig } from '../types/backtest'
import { WS_BASE } from '../config/api'

// 模块级单例 — strategy 页和 signals 页共享同一份回测状态
const status = shallowRef<'idle' | 'queued' | 'running' | 'completed' | 'failed'>('idle')
const progress = shallowRef(0)
const currentStep = shallowRef('')
const result = shallowRef<BacktestResult | null>(null)
const error = shallowRef<string | null>(null)

export function useBacktest() {
  async function run(config: BacktestConfig) {
    status.value = 'queued'
    progress.value = 0
    error.value = null

    try {
      const res = await $fetch<{ data: { run_id: string, status: string, ws_url: string } }>('/api/v1/backtest', {
        method: 'POST',
        body: config,
      })

      const { run_id, ws_url } = res.data
      status.value = 'running'

      // WebSocket 进度跟踪 — 直连 API 服务器 (Vite proxy 不代理 WS upgrade)
      const ws = new WebSocket(`${WS_BASE}${ws_url}`)

      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        progress.value = msg.progress ?? progress.value
        currentStep.value = msg.step ?? currentStep.value

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
    catch (e: any) {
      status.value = 'failed'
      error.value = e?.data?.error?.message ?? e?.message ?? '回测启动失败'
    }
  }

  async function fetchResult(runId: string) {
    try {
      const res = await $fetch<{ data: BacktestResult }>(`/api/v1/backtest/${runId}`)
      result.value = res.data
      status.value = res.data.status
    }
    catch (e: any) {
      status.value = 'failed'
      error.value = e?.message ?? '获取回测结果失败'
    }
  }

  return { status, progress, currentStep, result, error, run }
}
