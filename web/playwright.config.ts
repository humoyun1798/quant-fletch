import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  use: {
    headless: true,
  },
  // No webServer — start manually:
  //   API:   cd api && python -m uvicorn src.server.main:app --port 8000
  //   Nuxt:  cd web && pnpm dev
  // API tests hit port 8000 directly; browser tests hit port 3000 (Nuxt proxy)
})
