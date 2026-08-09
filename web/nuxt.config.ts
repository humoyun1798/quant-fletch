import { defineNuxtConfig } from 'nuxt/config'

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
    '/api/**': { proxy: 'http://localhost:8000/api/**' },
  },

  devtools: { enabled: true },
})
