/**
 * E2E tests for the Rotor API.
 *
 * Start the API server first:
 *   cd api && .venv/Scripts/python.exe -m uvicorn server.main:app --port 8000
 * Then run: pnpm test:e2e
 */
import { expect, test } from '@playwright/test'

const API = 'http://localhost:8000'

// ── Health ──────────────────────────────────────────────────────────

test.describe('Health API', () => {
  test('GET /health returns 200 with status ok', async ({ request }) => {
    const resp = await request.get(`${API}/health`)
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    expect(body.status).toBe('ok')
  })

  test('GET /health/detailed returns component statuses', async ({ request }) => {
    const resp = await request.get(`${API}/health/detailed`)
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    expect(body.data).toHaveProperty('duckdb')
    expect(body.data).toHaveProperty('postgres')
  })
})

// ── ETFs ────────────────────────────────────────────────────────────

test.describe('ETFs API', () => {
  test('GET /api/v1/etfs returns paginated etf list', async ({ request }) => {
    const resp = await request.get(`${API}/api/v1/etfs`)
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    expect(body).toHaveProperty('data')
    expect(body).toHaveProperty('meta')
    expect(Array.isArray(body.data)).toBe(true)
    expect(body.data.length).toBeGreaterThanOrEqual(25)

    // Each entry has required fields
    const first = body.data[0]
    expect(first).toHaveProperty('code')
    expect(first).toHaveProperty('name')
    expect(first).toHaveProperty('type')
    expect(first).toHaveProperty('latest_close')
  })

  test('GET /api/v1/etfs?per_page=5 respects pagination', async ({ request }) => {
    const resp = await request.get(`${API}/api/v1/etfs?per_page=5`)
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    expect(body.data.length).toBeLessThanOrEqual(5)
    expect(body.meta.per_page).toBe(5)
  })

  test('GET /api/v1/etfs/:code/ohlcv returns price data', async ({ request }) => {
    const resp = await request.get(`${API}/api/v1/etfs/510300.SH/ohlcv?days=30`)
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    // Response is { data: [...], meta: {...} }
    expect(body).toHaveProperty('data')
    expect(body).toHaveProperty('meta')
    expect(Array.isArray(body.data)).toBe(true)
    if (body.data.length > 0) {
      const row = body.data[0]
      expect(row).toHaveProperty('date')
      expect(row).toHaveProperty('close')
    }
  })

  test('GET /api/v1/etfs/INVALID/ohlcv returns 404', async ({ request }) => {
    const resp = await request.get(`${API}/api/v1/etfs/INVALID/ohlcv`)
    expect(resp.status()).toBe(404)
  })
})

// ── Strategies ──────────────────────────────────────────────────────

test.describe('Strategies API', () => {
  test('GET /api/v1/strategies returns all 5 strategies', async ({ request }) => {
    const resp = await request.get(`${API}/api/v1/strategies`)
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    expect(body).toHaveProperty('data')
    expect(Array.isArray(body.data)).toBe(true)
    expect(body.data.length).toBe(5)

    // Verify known strategy names
    const names = body.data.map((s: { name: string }) => s.name)
    expect(names).toContain('双均线动量轮动')
    expect(names).toContain('波动率加权风险平价')
    expect(names).toContain('带止损动量增强')
    expect(names).toContain('多因子综合打分')
    expect(names).toContain('趋势+均线择时')
  })

  test('each strategy entry has params, factors, and meta', async ({ request }) => {
    const resp = await request.get(`${API}/api/v1/strategies`)
    const body = await resp.json()
    for (const s of body.data) {
      expect(s).toHaveProperty('name')
      expect(s).toHaveProperty('description')
      expect(s).toHaveProperty('version')
      expect(Array.isArray(s.params)).toBe(true)
      expect(Array.isArray(s.factors)).toBe(true)
    }
  })
})

// ── Backtest ────────────────────────────────────────────────────────

test.describe('Backtest API', () => {
  test('POST /api/v1/backtest creates a run and returns run_id', async ({ request }) => {
    const resp = await request.post(`${API}/api/v1/backtest`, {
      data: {
        strategy: '双均线动量轮动',
        params: { lookback: 30, top_n: 3, rebalance: 'weekly' },
        start_date: '2026-01-01',
        end_date: '2026-06-30',
        benchmark: '510300.SH',
      },
    })
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    // Response is wrapped in { data: { run_id, status, ws_url } }
    expect(body).toHaveProperty('data')
    expect(body.data).toHaveProperty('run_id')
    expect(typeof body.data.run_id).toBe('string')
  })

  test('POST /api/v1/backtest with unknown strategy returns 422', async ({ request }) => {
    const resp = await request.post(`${API}/api/v1/backtest`, {
      data: {
        strategy: '不存在的策略',
        params: {},
        start_date: '2026-01-01',
        end_date: '2026-06-30',
        benchmark: '510300.SH',
      },
    })
    expect(resp.status()).toBe(422)
  })

  test('POST /api/v1/backtest with out-of-range param returns 422', async ({ request }) => {
    const resp = await request.post(`${API}/api/v1/backtest`, {
      data: {
        strategy: '双均线动量轮动',
        params: { lookback: 9999, top_n: 3, rebalance: 'weekly' },
        start_date: '2026-01-01',
        end_date: '2026-06-30',
        benchmark: '510300.SH',
      },
    })
    expect(resp.status()).toBe(422)
  })

  test('GET /api/v1/backtest/:run_id returns completed result', async ({ request }) => {
    // Create a backtest run
    const createResp = await request.post(`${API}/api/v1/backtest`, {
      data: {
        strategy: '双均线动量轮动',
        params: { lookback: 30, top_n: 3, rebalance: 'weekly' },
        start_date: '2026-01-01',
        end_date: '2026-04-30',
        benchmark: '510300.SH',
      },
    })
    expect(createResp.status()).toBe(200)
    const { data: created } = await createResp.json()
    const run_id = created.run_id

    // Poll for completion (up to 15s)
    let result: Record<string, unknown> | null = null
    for (let i = 0; i < 15; i++) {
      const statusResp = await request.get(`${API}/api/v1/backtest/${run_id}`)
      if (statusResp.status() === 200) {
        const body = await statusResp.json()
        if (body.status === 'completed' || body.data?.status === 'completed') {
          result = body.data || body
          break
        }
      }
      await new Promise(r => setTimeout(r, 1000))
    }
    expect(result).not.toBeNull()
    expect(result).toHaveProperty('metrics')
    expect(result.metrics).toHaveProperty('total_return')
  })

  test('GET /api/v1/backtest/:run_id with unknown id returns 404', async ({ request }) => {
    const resp = await request.get(`${API}/api/v1/backtest/nonexistent-id`)
    expect(resp.status()).toBe(404)
  })
})

// ── System ──────────────────────────────────────────────────────────

test.describe('System API', () => {
  test('GET /api/v1/system/status returns data status', async ({ request }) => {
    const resp = await request.get(`${API}/api/v1/system/status`)
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    expect(body).toHaveProperty('data')
    expect(body.data).toHaveProperty('status')
    expect(body.data).toHaveProperty('etfs_available')
    expect(body.data).toHaveProperty('etfs_total')
  })
})
