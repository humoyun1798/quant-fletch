// @env browser
// fetch from Nuxt proxy → FastAPI, error handling inline
import { shallowRef } from '#imports'
import type { ETF, OHLCV, Bar, BarPeriod } from '../types/etf'

export function useETFData() {
  const etfs = shallowRef<ETF[]>([])
  const loading = shallowRef(false)
  const error = shallowRef<string | null>(null)

  async function fetchAll() {
    loading.value = true
    error.value = null
    try {
      const res = await $fetch<{ data: ETF[] }>('/api/v1/etfs')
      etfs.value = res.data
    }
    catch (e: any) {
      error.value = e?.message ?? '获取 ETF 列表失败'
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
      return res.data
    }
    catch (e: any) {
      error.value = e?.message ?? '获取 K 线数据失败'
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
      return res.data
    }
    catch (e: any) {
      error.value = e?.message ?? '获取 K 线数据失败'
      return []
    }
    finally {
      loading.value = false
    }
  }

  return { etfs, loading, error, fetchAll, fetchOHLCV, fetchBars }
}
