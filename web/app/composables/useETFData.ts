// @env browser
// ETF 数据获取 — fetch from Nuxt proxy → FastAPI
// 依据: 07-前端设计.md §Composable 设计
import { $fetch } from '#build/fetch.mjs'
import { ref, shallowRef } from '#imports'
import type { Bar, BarPeriod, ETF, OHLCV } from '../types/etf'

export function useETFData() {
  const etfs = shallowRef<ETF[]>([])
  const ohlcv = shallowRef<OHLCV[]>([])
  const bars = shallowRef<Bar[]>([])
  const loading = ref(false)
  const error = shallowRef<string | null>(null)

  async function fetchAll() {
    loading.value = true
    error.value = null
    try {
      const res = await $fetch<{ data: ETF[] }>('/api/v1/etfs')
      etfs.value = res.data
    }
    catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '获取 ETF 列表失败'
      error.value = msg
    }
    finally {
      loading.value = false
    }
  }

  async function fetchOHLCV(code: string, start: string, end: string) {
    loading.value = true
    error.value = null
    try {
      const res = await $fetch<{ data: OHLCV[] }>(`/api/v1/etfs/${code}/ohlcv`, {
        query: { start, end },
      })
      ohlcv.value = res.data
      return res.data
    }
    catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '获取 K 线数据失败'
      error.value = msg
      ohlcv.value = []
      return []
    }
    finally {
      loading.value = false
    }
  }

  async function fetchBars(code: string, period: BarPeriod = 'daily') {
    loading.value = true
    error.value = null
    try {
      const res = await $fetch<{ data: Bar[] }>(`/api/v1/etfs/${code}/bars`, {
        query: { period },
      })
      bars.value = res.data
      return res.data
    }
    catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '获取 K 线数据失败'
      error.value = msg
      bars.value = []
      return []
    }
    finally {
      loading.value = false
    }
  }

  return { etfs, ohlcv, bars, loading, error, fetchAll, fetchOHLCV, fetchBars }
}
