import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useETFData } from '../../app/composables/useETFData'

const mockFetch = vi.fn()
vi.mock('#build/fetch.mjs', () => ({
  $fetch: (...args: unknown[]) => mockFetch(...args),
}))

const mockETFs = [
  {
    code: '510300.SH',
    name: '沪深300ETF',
    type: 'broad' as const,
    underlying: '沪深300',
    inception: '2012-05-28',
    expense: 0.5,
    latest_date: '2024-03-31',
    latest_close: 3.85,
    change_pct: 0.5,
  },
  {
    code: '159915.SZ',
    name: '创业板ETF',
    type: 'broad' as const,
    underlying: '创业板指',
    inception: '2011-06-01',
    expense: 0.6,
    latest_date: '2024-03-31',
    latest_close: 2.45,
    change_pct: -0.3,
  },
]

describe('useETFData', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('initial state is empty', () => {
    const { etfs, loading, error } = useETFData()
    expect(etfs.value).toEqual([])
    expect(loading.value).toBe(false)
    expect(error.value).toBeNull()
  })

  it('fetchAll populates etfs and clears loading', async () => {
    mockFetch.mockResolvedValue({ data: mockETFs })

    const { etfs, loading, error, fetchAll } = useETFData()
    const promise = fetchAll()
    expect(loading.value).toBe(true)
    await promise
    expect(etfs.value).toEqual(mockETFs)
    expect(loading.value).toBe(false)
    expect(error.value).toBeNull()
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/etfs')
  })

  it('fetchAll sets error on failure', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'))
    const { etfs, error, loading, fetchAll } = useETFData()
    await fetchAll()
    expect(etfs.value).toEqual([])
    expect(loading.value).toBe(false)
    expect(error.value).toBe('Network error')
  })

  it('fetchOHLCV returns data array', async () => {
    const ohlcvData = [{ date: '2024-01-01', open: 1, high: 2, low: 0.5, close: 1.5, volume: 1000 }]
    mockFetch.mockResolvedValue({ data: ohlcvData })
    const { fetchOHLCV } = useETFData()
    const result = await fetchOHLCV('510300.SH', '2024-01-01', '2024-01-31')
    expect(result).toEqual(ohlcvData)
  })

  it('fetchOHLCV returns empty on error', async () => {
    mockFetch.mockRejectedValue(new Error('Not found'))
    const { fetchOHLCV, error } = useETFData()
    const result = await fetchOHLCV('NONEXIST', '2024-01-01', '2024-01-31')
    expect(result).toEqual([])
    expect(error.value).toBe('Not found')
  })
})
