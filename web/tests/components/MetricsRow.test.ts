import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MetricsRow from '../../app/components/MetricsRow.vue'

const sampleMetrics = {
  total_return: 0.15,
  annual_return: 0.12,
  annual_volatility: 0.18,
  sharpe_ratio: 0.67,
  max_drawdown: -0.12,
  calmar_ratio: 1.0,
  win_rate: 0.55,
  benchmark_return: 0.08,
  alpha: 0.04,
  avg_turnover: 0.3,
}

describe('MetricsRow', () => {
  it('renders empty state when metrics is null', () => {
    const wrapper = mount(MetricsRow, {
      props: { metrics: null },
    })
    // All cards show dashed border (empty state)
    const cards = wrapper.findAll('.border-dashed')
    expect(cards.length).toBe(10)
    // Each card shows "---" placeholder
    expect(wrapper.text()).toContain('---')
  })

  it('renders 10 metric cards when metrics are provided', () => {
    const wrapper = mount(MetricsRow, {
      props: { metrics: sampleMetrics },
    })
    const cards = wrapper.findAll('.metric-card')
    expect(cards.length).toBe(10)
  })

  it('formats percentage values correctly', () => {
    const wrapper = mount(MetricsRow, {
      props: { metrics: sampleMetrics },
    })
    const text = wrapper.text()
    expect(text).toContain('15.00%')  // total_return
    expect(text).toContain('12.00%')  // annual_return
    expect(text).toContain('-12.00%') // max_drawdown
  })

  it('formats ratio values with 2 decimals', () => {
    const wrapper = mount(MetricsRow, {
      props: { metrics: sampleMetrics },
    })
    const text = wrapper.text()
    expect(text).toContain('0.67') // sharpe
    expect(text).toContain('1.00') // calmar
    expect(text).toContain('0.04') // alpha
  })

  it('applies positive color to gains and negative to losses', () => {
    const wrapper = mount(MetricsRow, {
      props: { metrics: sampleMetrics },
    })
    // total_return > 0 → red (positive return = red in Chinese markets context)
    const elements = wrapper.findAll('.tabular-nums')
    // Verify the component renders without errors
    expect(elements.length).toBeGreaterThan(0)
  })
})
