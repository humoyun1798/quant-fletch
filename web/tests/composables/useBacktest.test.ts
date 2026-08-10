import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useBacktest } from '../../app/composables/useBacktest'

const mockFetch = vi.fn()
vi.mock('#build/fetch.mjs', () => ({
  $fetch: (...args: unknown[]) => mockFetch(...args),
}))

// Stub WebSocket — jsdom does not provide it
class MockWebSocket {
  url: string
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  close = vi.fn()
  constructor(url: string) { this.url = url }
}
vi.stubGlobal('WebSocket', MockWebSocket)

describe('useBacktest', () => {
  beforeEach(() => {
    mockFetch.mockReset()
    // Reset module-level state
    const { status, progress, result, error } = useBacktest()
    status.value = 'idle'
    progress.value = 0
    result.value = null
    error.value = null
  })

  it('initial state is idle', () => {
    const { status, progress, result, error } = useBacktest()
    expect(status.value).toBe('idle')
    expect(progress.value).toBe(0)
    expect(result.value).toBeNull()
    expect(error.value).toBeNull()
  })

  it('run sets status to queued then calls API', async () => {
    mockFetch.mockResolvedValue({
      data: { run_id: 'test-run-id', status: 'queued', ws_url: '/ws/test' },
    })

    const { status, run } = useBacktest()
    const config = {
      strategy: 'momentum',
      params: { lookback: 60 },
      start_date: '2024-01-01',
      end_date: '2024-03-31',
      benchmark: '510300.SH',
    }

    // Fire-and-forget pattern: run() returns void, status set synchronously
    run(config)
    expect(status.value).toBe('queued')
  })

  it('run handles fetch error and sets failed status', async () => {
    mockFetch.mockRejectedValue({
      data: { error: { message: '策略不存在' } },
    })

    const { status, error, run } = useBacktest()
    const config = {
      strategy: 'invalid',
      params: {},
      start_date: '2024-01-01',
      end_date: '2024-03-31',
      benchmark: '510300.SH',
    }

    await run(config)
    expect(status.value).toBe('failed')
    expect(error.value).toBe('策略不存在')
  })

  it('run handles generic error fallback', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'))

    const { status, error, run } = useBacktest()
    const config = {
      strategy: 'test',
      params: {},
      start_date: '2024-01-01',
      end_date: '2024-03-31',
      benchmark: '510300.SH',
    }

    await run(config)
    expect(status.value).toBe('failed')
    expect(error.value).toBe('Network error')
  })
})
