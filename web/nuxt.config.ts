import { defineNuxtConfig } from 'nuxt/config'

// 后端地址: 本地开发直连 localhost:8000; 容器内需指向 compose 的 api 服务。
// routeRules 的 proxy 目标是构建期求值并写死进产物, 所以 Dockerfile.web 必须在
// `nuxt build` 之前注入 API_BASE_URL, 仅靠 compose 的 runtime environment 无效。
const apiBase = process.env.API_BASE_URL || 'http://localhost:8000'

export default defineNuxtConfig({
  modules: [
    '@unocss/nuxt',
    '@nuxt/eslint',
    '@vueuse/nuxt',
    'nuxt-mcp-dev',
    'nuxt-eslint-auto-explicit-import',
  ],

  imports: {
    autoImport: false,
  },
  components: {
    dirs: [],
  },
  nitro: {
    imports: false,
  },

  app: {
    pageTransition: false,
  },

  routeRules: {
    '/api/**': { proxy: `${apiBase}/api/**` },
  },

  devtools: { enabled: true },

  vite: {
    optimizeDeps: {
      include: ['floating-vue', 'reka-ui', 'splitpanes', '@antfu/utils'],
      exclude: ['@antfu/design'],
    },
  },
})
