import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useStrategy } from '../../app/composables/useStrategy'
import type { StrategyMeta } from '../../app/types/strategy'

const mockFetch = vi.fn()
vi.mock('ofetch', () => ({
  $fetch: (...args: unknown[]) => mockFetch(...args),
}))

const mockStrategies: StrategyMeta[] = [
  {
    name: '双均线动量轮动',
    version: '1.0.0',
    author: 'quant-fletch',
    description: '买入过去 N 日动量最强的 ETF',
    tags: ['动量', 'ETF'],
    min_bars: 60,
    rebalance_freq: 'weekly',
    params: [
      { name: 'lookback', default: 60, type: 'int', min: 10, max: 250, description: '回看天数' },
      { name: 'top_n', default: 5, type: 'int', min: 1, max: 15, description: '持仓数' },
      { name: 'rebalance', default: 'weekly', type: 'choice', choices: ['daily', 'weekly', 'monthly'], description: '调仓频率' },
    ],
    factors: [{ name: 'momentum', description: '动量因子', category: 'momentum' }],
  },
  {
    name: '波动率加权风险平价',
    version: '1.0.0',
    author: 'quant-fletch',
    description: '按波动率倒数分配权重',
    tags: ['风险平价', '波动率'],
    min_bars: 30,
    rebalance_freq: 'monthly',
    params: [],
    factors: [],
  },
]

describe('useStrategy', () => {
  beforeEach(() => {
    mockFetch.mockReset()
    // Reset module state between tests
    const { strategies, selected, params } = useStrategy()
    strategies.value = []
    selected.value = null
    params.value = {}
  })

  it('initial state is empty', () => {
    const { strategies, selected, params } = useStrategy()
    expect(strategies.value).toEqual([])
    expect(selected.value).toBeNull()
    expect(params.value).toEqual({})
  })

  it('fetchAll populates strategies', async () => {
    mockFetch.mockResolvedValue({ data: mockStrategies })

    const { strategies, fetchAll } = useStrategy()
    await fetchAll()

    expect(strategies.value).toEqual(mockStrategies)
  })

  it('fetchAll handles error gracefully', async () => {
    mockFetch.mockRejectedValue(new Error('Server error'))

    const { strategies, fetchAll } = useStrategy()
    await fetchAll()

    // Error is caught, falls back to empty
    expect(strategies.value).toEqual([])
  })

  it('selectStrategy sets selected and builds default params', () => {
    // Pre-populate the module state
    const { strategies } = useStrategy()
    strategies.value = mockStrategies

    const { selected, params, selectStrategy } = useStrategy()
    selectStrategy('双均线动量轮动')

    expect(selected.value).toBe('双均线动量轮动')
    expect(params.value).toEqual({
      lookback: 60,
      top_n: 5,
      rebalance: 'weekly',
    })
  })

  it('selectStrategy ignores unknown strategy', () => {
    const { selected, selectStrategy } = useStrategy()
    selectStrategy('nonexistent')

    expect(selected.value).toBeNull()
  })
})
