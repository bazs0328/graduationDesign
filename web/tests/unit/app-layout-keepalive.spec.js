import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { defineComponent, h, nextTick, onActivated, onDeactivated, onMounted } from 'vue'

import AppLayout from '@/layout/AppLayout.vue'

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

function createTrackedPage(label, counters) {
  return defineComponent({
    name: `${label}Page`,
    setup() {
      onMounted(() => {
        counters.mounted += 1
      })
      onActivated(() => {
        counters.activated += 1
      })
      onDeactivated(() => {
        counters.deactivated += 1
      })
      return () => h('div', { 'data-test': label }, label)
    },
  })
}

beforeEach(() => {
  localStorage.clear()
})

describe('AppLayout keep-alive routing', () => {
  it('caches routed pages and reuses them on navigation back', async () => {
    const pageACounters = { mounted: 0, activated: 0, deactivated: 0 }
    const pageBCounters = { mounted: 0, activated: 0, deactivated: 0 }
    const PageA = createTrackedPage('page-a', pageACounters)
    const PageB = createTrackedPage('page-b', pageBCounters)

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', name: 'A', meta: { title: 'A' }, component: PageA },
        { path: '/b', name: 'B', meta: { title: 'B' }, component: PageB },
      ],
    })

    await router.push('/')
    await router.isReady()

    const wrapper = mount(AppLayout, {
      global: {
        plugins: [router],
        stubs: {
          AppSidebar: { template: '<aside data-test="sidebar"></aside>' },
        },
      },
    })

    await flushPromises()
    await nextTick()

    expect(pageACounters.mounted).toBe(1)
    expect(pageACounters.activated).toBe(1)
    expect(pageACounters.deactivated).toBe(0)

    await router.push('/b')
    await flushPromises()
    await nextTick()

    expect(pageACounters.mounted).toBe(1)
    expect(pageACounters.deactivated).toBe(1)
    expect(pageBCounters.mounted).toBe(1)
    expect(pageBCounters.activated).toBe(1)

    await router.push('/')
    await flushPromises()
    await nextTick()

    expect(pageACounters.mounted).toBe(1)
    expect(pageACounters.activated).toBe(2)
    expect(pageBCounters.mounted).toBe(1)
    expect(pageBCounters.deactivated).toBe(1)

    expect(wrapper.text()).toContain('page-a')
  })
})

