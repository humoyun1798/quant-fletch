/* eslint-disable unimport/auto-insert */
// Mock for #build/fetch.mjs — tests override $fetch via vi.mock
export const $fetch = () => Promise.resolve({ data: [] })
