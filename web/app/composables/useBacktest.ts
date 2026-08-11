// @env browser
// 回测执行 — 模块级单例，strategy 页和 signals 页共享回测状态
// 依据: 05-回测引擎.md §前端集成 + 07-前端设计.md §Composable 设计
import { $fetch } from 'ofetch'
import { ref, shallowRef } from '#imports'
import type { BacktestResult, BacktestConfig } from '../types/backtest'
import { WS_BASE } from '../config/api'

const status = shallowRef<'idle' | 'queued' | 'running' | 'completed' | 'failed'>('idle')
const progress = ref(0)
const currentStep = shallowRef('')
const currentDate = shallowRef('')
const result = shallowRef<BacktestResult | null>(null)
const error = shallowRef<string | null>(null)

// 跟踪活跃 WebSocket，确保旧连接在新 run 前关闭
let _activeWs: WebSocket | null = null
let _activeRunId: string | null = null

export function useBacktest() {
  async function run(config: BacktestConfig) {
    // 关闭上一次未完成的 WebSocket 连接
    if (_activeWs && _activeWs.readyState !== WebSocket.CLOSED) {
      _activeWs.close()
      _activeWs = null
    }

    // 重置全部状态（包括 result，防止旧结果泄漏到新 run）
    status.value = 'queued'
    progress.value = 0
    currentStep.value = ''
    currentDate.value = ''
    result.value = null
    error.value = null
    _activeRunId = null

    try {
      const res = await $fetch<{ data: { run_id: string, status: string, ws_url: string } }>('/api/v1/backtest', {
        method: 'POST',
        body: config,
      })

      const { run_id, ws_url } = res.data
      _activeRunId = run_id
      status.value = 'running'

      // WebSocket 直连 API 服务器（不走 Nitro 代理）
      const ws = new WebSocket(`${WS_BASE}${ws_url}`)
      _activeWs = ws

      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        progress.value = msg.progress ?? progress.value
        currentStep.value = msg.step ?? currentStep.value
        currentDate.value = msg.current_date ?? currentDate.value

        if (msg.step === 'completed') {
          ws.close()
          _activeWs = null
          fetchResult(run_id)
        }
        else if (msg.step === 'failed') {
          ws.close()
          _activeWs = null
          status.value = 'failed'
          error.value = msg.message ?? '回测执行失败'
        }
      }

      ws.onerror = () => {
        ws.close()
        _activeWs = null
        status.value = 'failed'
        error.value = 'WebSocket 连接失败'
      }

      ws.onclose = () => {
        _activeWs = null
        // WebSocket 意外关闭但未收到 completed/failed 消息时，尝试 GET 拉取结果
        if (status.value === 'running' && _activeRunId === run_id) {
          fetchResult(run_id)
        }
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

  function reset() {
    // 关闭活跃 WebSocket
    if (_activeWs && _activeWs.readyState !== WebSocket.CLOSED) {
      _activeWs.close()
      _activeWs = null
    }
    status.value = 'idle'
    progress.value = 0
    currentStep.value = ''
    currentDate.value = ''
    result.value = null
    error.value = null
    _activeRunId = null
  }

  return { status, progress, currentStep, currentDate, result, error, run, reset }
}
