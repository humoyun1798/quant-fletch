// Minimal mock for @vueuse/core — only exports used by composables under test
import { ref } from 'vue'

export const usePreferredReducedMotion = () => ref(false)
