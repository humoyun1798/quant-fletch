/**
 * Browser E2E tests for the Rotor Nuxt frontend.
 *
 * Prerequisites:
 *   API:   cd api && .venv/Scripts/python.exe -m uvicorn server.main:app --port 8000
 *   Nuxt:  cd web && pnpm dev
 * Then run: pnpm test:e2e
 */
import { expect, test } from '@playwright/test'

const APP = 'http://localhost:3000'

// ── Navigation & Routing ──────────────────────────────────────────────

test.describe('App routing', () => {
  test('index redirects to /dashboard', async ({ page }) => {
    await page.goto(`${APP}/`)
    await page.waitForURL('**/dashboard')
    expect(page.url()).toContain('/dashboard')
  })

  test('/dashboard loads without crash', async ({ page }) => {
    const resp = await page.goto(`${APP}/dashboard`)
    expect(resp?.status()).toBe(200)
  })

  test('/strategy loads without crash', async ({ page }) => {
    const resp = await page.goto(`${APP}/strategy`)
    expect(resp?.status()).toBe(200)
  })
})

// ── Dashboard Content ─────────────────────────────────────────────────

test.describe('Dashboard page', () => {
  test('renders page title', async ({ page }) => {
    await page.goto(`${APP}/dashboard`)
    // Nuxt app should have some visible content
    await expect(page.locator('body')).not.toBeEmpty()
  })

  test('dashboard-grid container is present', async ({ page }) => {
    await page.goto(`${APP}/dashboard`)
    const grid = page.locator('.dashboard-grid')
    await expect(grid).toBeVisible()
  })
})

// ── API Proxy Through Nuxt ────────────────────────────────────────────

test.describe('API proxy', () => {
  // NOTE: /health is mounted directly on the FastAPI app (no /api prefix),
  // so it's NOT reachable through the Nuxt /api/** → backend proxy.
  // It is reachable directly at http://localhost:8000/health.

  test('GET /api/v1/etfs proxied through Nuxt', async ({ request }) => {
    const resp = await request.get(`${APP}/api/v1/etfs`)
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    expect(body).toHaveProperty('data')
    expect(Array.isArray(body.data)).toBe(true)
  })

  test('GET /api/v1/strategies proxied through Nuxt', async ({ request }) => {
    const resp = await request.get(`${APP}/api/v1/strategies`)
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    expect(body).toHaveProperty('data')
  })

  test('POST /api/v1/backtest validation through proxy', async ({ request }) => {
    const resp = await request.post(`${APP}/api/v1/backtest`, {
      data: { strategy: 'nonexistent' },
    })
    expect(resp.status()).toBe(422)
  })
})
