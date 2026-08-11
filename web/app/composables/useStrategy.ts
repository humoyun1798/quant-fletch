// @env browser
// 策略管理 — 模块级单例，所有组件共享策略列表和选中状态
// 依据: 07-前端设计.md §Composable 设计
import { $fetch } from 'ofetch'
import { ref, shallowRef } from '#imports'
import type { StrategyMeta } from '../types/strategy'

const strategies = shallowRef<StrategyMeta[]>([])
const selected = ref<string | null>(null)
const params = shallowRef<Record<string, number | string>>({})
let _pending: Promise<void> | null = null

export function useStrategy() {
  async function fetchAll() {
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

  function updateParam(key: string, value: number | string) {
    if (params.value[key] === value) return
    params.value = { ...params.value, [key]: value }
  }

  return { strategies, selected, params, fetchAll, selectStrategy, updateParam }
}
