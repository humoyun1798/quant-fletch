// Minimal mock for @vueuse/core — only exports used by composables under test
import { usePreferredReducedMotion } from '@vueuse/core'
import { ref } from 'vue'

export const usePreferredReducedMotion = () => ref(false)
