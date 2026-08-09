import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useBacktest } from '../../app/composables/useBacktest'

describe('useBacktest', () => {
  beforeEach(() => {
    vi.stubGlobal('$fetch', vi.fn())
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
    vi.stubGlobal('$fetch', vi.fn().mockResolvedValue({
      data: { run_id: 'test-run-id', status: 'queued', ws_url: '/ws/test' },
    }))

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
    vi.stubGlobal('$fetch', vi.fn().mockRejectedValue({
      data: { error: { message: '策略不存在' } },
    }))

    const { status, error, run } = useBacktest()
    const config = {
      strategy: 'invalid',
      params: {},
      start_date: '2024-01-01',
      end_date: '2024-03-31',
      benchmark: '510300.SH',
    }

    await run(config)
    // After the async rejection is caught
    expect(status.value).toBe('failed')
    expect(error.value).toBe('策略不存在')
  })
})
