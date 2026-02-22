import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { h, markRaw } from 'vue'

import EmptyState from '@/components/ui/EmptyState.vue'

const DummyIcon = markRaw({
  name: 'DummyIcon',
  render() {
    return h('svg', { 'data-testid': 'dummy-icon' })
  },
})

describe('EmptyState', () => {
  it('renders title, description, hint, and icon', () => {
    const wrapper = mount(EmptyState, {
      props: {
        icon: DummyIcon,
        title: '空状态标题',
        description: '描述信息',
        hint: '提示信息',
      },
    })

    expect(wrapper.text()).toContain('空状态标题')
    expect(wrapper.text()).toContain('描述信息')
    expect(wrapper.text()).toContain('提示信息')
    expect(wrapper.find('[data-testid="dummy-icon"]').exists()).toBe(true)
  })

  it('applies size and align variants', () => {
    const wrapper = mount(EmptyState, {
      props: {
        title: 'T',
        size: 'sm',
        align: 'left',
      },
    })

    const rootClasses = wrapper.get('[data-empty-state]').classes()
    expect(rootClasses).toContain('items-start')
    expect(rootClasses).toContain('py-6')
  })

  it('shows action buttons and emits primary/secondary', async () => {
    const wrapper = mount(EmptyState, {
      props: {
        title: '带动作',
        primaryAction: { label: '主操作' },
        secondaryAction: { label: '次操作', variant: 'outline' },
      },
    })

    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(2)
    expect(wrapper.text()).toContain('主操作')
    expect(wrapper.text()).toContain('次操作')

    await buttons[0].trigger('click')
    await buttons[1].trigger('click')

    expect(wrapper.emitted('primary')).toHaveLength(1)
    expect(wrapper.emitted('secondary')).toHaveLength(1)
  })

  it('renders without action buttons', () => {
    const wrapper = mount(EmptyState, {
      props: {
        title: '无动作',
      },
      slots: {
        default: '补充说明',
      },
    })

    expect(wrapper.text()).toContain('补充说明')
    expect(wrapper.findAll('button')).toHaveLength(0)
  })
})
