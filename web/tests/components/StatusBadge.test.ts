import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusBadge from '../../app/components/StatusBadge.vue'

describe('StatusBadge', () => {
  const statuses = ['queued', 'running', 'completed', 'failed', 'idle'] as const

  it('renders each status with correct label', () => {
    const expectedLabels: Record<string, string> = {
      queued: '排队中',
      running: '运行中',
      completed: '已完成',
      failed: '失败',
      idle: '空闲',
    }

    for (const status of statuses) {
      const wrapper = mount(StatusBadge, {
        props: { status },
      })
      expect(wrapper.text()).toContain(expectedLabels[status])
    }
  })

  it('applies correct color classes for each variant', () => {
    const expectedColors: Record<string, string[]> = {
      queued: ['color-yellow-500'],
      running: ['color-blue-500'],
      completed: ['color-green-500'],
      failed: ['color-red-500'],
      idle: ['op-fade'],
    }

    for (const status of statuses) {
      const wrapper = mount(StatusBadge, {
        props: { status },
      })
      const span = wrapper.find('span')
      for (const cls of expectedColors[status]) {
        expect(span.classes()).toContain(cls)
      }
    }
  })

  it('renders spinning icon for running status', () => {
    const wrapper = mount(StatusBadge, {
      props: { status: 'running' },
    })
    expect(wrapper.find('.animate-spin').exists()).toBe(true)
  })

  it('renders static icon for non-running status', () => {
    const wrapper = mount(StatusBadge, {
      props: { status: 'completed' },
    })
    expect(wrapper.find('.animate-spin').exists()).toBe(false)
    expect(wrapper.find('.i-ph-check-circle-duotone').exists()).toBe(true)
  })
})
