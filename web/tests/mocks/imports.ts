// Mock for Nuxt #imports — provides the subset used by composables under test
import { shallowRef, ref, computed, watch } from 'vue'

// Re-export everything from vue that composables might need
export { shallowRef, ref, computed, watch }

// Mock Nuxt-specific utilities
export const useNuxtApp = () => ({
  $gsap: null,
})

// Mock $fetch — tests override via vi.stubGlobal
export const useFetch = () => ({})
export const useRuntimeConfig = () => ({})
export const navigateTo = () => {}
export const useRouter = () => ({ push: () => {}, replace: () => {} })
export const useRoute = () => ({ params: {}, query: {} })

// Allow tests to also import directly from vue
export * from 'vue'
