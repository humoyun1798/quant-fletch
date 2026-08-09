// @env browser
import { shallowRef } from '#imports'
import type { StrategyMeta } from '../types/strategy'

// 模块级单例 — 所有组件共享同一份策略列表和选中状态
const strategies = shallowRef<StrategyMeta[]>([])
const selected = shallowRef<string | null>(null)
const params = shallowRef<Record<string, any>>({})
let _pending: Promise<void> | null = null

export function useStrategy() {
  async function fetchAll() {
    // 去重 guard — 同时调多次只发一次请求
    if (_pending) return _pending
    _pending = (async () => {
      try {
        const res = await $fetch<{ data: StrategyMeta[] }>('/api/v1/strategies')
        strategies.value = res.data
      }
      catch {
        strategies.value = []
      }
      finally {
        _pending = null
      }
    })()
    return _pending
  }

  function selectStrategy(name: string) {
    const s = strategies.value.find(st => st.name === name)
    if (!s) return
    selected.value = name
    params.value = Object.fromEntries(
      s.params.map(p => [p.name, p.default]),
    )
  }

  return { strategies, selected, params, fetchAll, selectStrategy }
}
