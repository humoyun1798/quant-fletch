/* eslint-disable unimport/auto-insert */
// Mock for Nuxt #imports — provides the subset used by composables under test
import { ref, shallowRef, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

// Re-export everything from vue that composables might need
export { ref, shallowRef, computed, watch, onMounted, onUnmounted, nextTick }

// Mock Nuxt-specific utilities
export const useNuxtApp = () => ({
  $gsap: null,
})

// Mock $fetch — tests override via vi.mock
export const useFetch = () => ({})
export const useRuntimeConfig = () => ({})
export const navigateTo = () => {}
export const useRouter = () => ({ push: () => {}, replace: () => {} })
export const useRoute = () => ({ params: {}, query: {} })

// Allow tests to also import directly from vue
export * from 'vue'
