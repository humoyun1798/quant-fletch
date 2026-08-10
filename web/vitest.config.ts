import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'node:path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '#imports': resolve(__dirname, 'tests/mocks/imports.ts'),
      '#build/fetch.mjs': resolve(__dirname, 'tests/mocks/fetch.ts'),
      '#app/composables/router': resolve(__dirname, 'tests/mocks/imports.ts'),
      '@vueuse/core': resolve(__dirname, 'tests/mocks/vueuse.ts'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['**/*.{test,spec}.?(c|m)[jt]s?(x)'],
    exclude: ['**/e2e/**', '**/node_modules/**'],
    coverage: {
      provider: 'v8',
      include: ['app/composables/**'],
      reporter: ['text', 'lcov'],
    },
  },
})
