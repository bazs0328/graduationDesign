import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

import App from '@/App.vue'
import { routes } from '@/router'
import { apiGet, apiPost, buildLearningPath, getProfile } from '@/api'

vi.mock('vue-echarts', () => ({
  default: {
    name: 'VChart',
    template: '<div data-test="vchart"></div>',
  },
}))

vi.mock('@/api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    getProfile: vi.fn(),
    buildLearningPath: vi.fn(),
  }
})

const kbFixture = { id: 'kb-1', name: '默认知识库' }

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

function parsePath(path) {
  return new URL(path, 'http://localhost')
}

function makeActivityItems(startIndex, count, total = 35) {
  return Array.from({ length: count }, (_, idx) => {
    const itemNo = startIndex + idx + 1
    return {
      type: 'question_asked',
      timestamp: new Date(Date.UTC(2026, 1, 22, 12, 0, total - itemNo)).toISOString(),
      doc_id: `doc-${itemNo}`,
      doc_name: `文档 ${itemNo}`,
      detail: `动态 ${itemNo}`,
      score: null,
      total: null,
    }
  })
}

async function mountAppWithRouter(initialPath = '/') {
  localStorage.setItem('gradtutor_user_id', 'test')
  localStorage.setItem('gradtutor_user', 'test')
  localStorage.setItem('gradtutor_access_token', 'test-token')
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes,
  })
  await router.push(initialPath)
  await router.isReady()
  const wrapper = mount(App, {
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  await nextTick()
  return { wrapper, router }
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  getProfile.mockReset()
  buildLearningPath.mockReset()
  localStorage.clear()

  getProfile.mockResolvedValue({ ability_level: 'intermediate' })
  buildLearningPath.mockResolvedValue({})
  apiPost.mockResolvedValue({})

  apiGet.mockImplementation((path) => {
    const url = parsePath(path)
    if (url.pathname === '/api/kb') {
      return Promise.resolve([kbFixture])
    }
    if (url.pathname === '/api/progress') {
      return Promise.resolve({
        total_docs: 1,
        total_quizzes: 0,
        total_attempts: 0,
        total_questions: 0,
        total_summaries: 0,
        total_keypoints: 0,
        avg_score: 0,
        last_activity: null,
        by_kb: [],
      })
    }
    if (url.pathname === '/api/activity') {
      const offset = Number(url.searchParams.get('offset') || 0)
      const limit = Number(url.searchParams.get('limit') || 30)
      if (offset >= 30) {
        return Promise.resolve({
          items: makeActivityItems(30, 5),
          total: 35,
          offset,
          limit,
          has_more: false,
        })
      }
      return Promise.resolve({
        items: makeActivityItems(0, 30),
        total: 35,
        offset,
        limit,
        has_more: true,
      })
    }
    if (url.pathname === '/api/recommendations') {
      return Promise.resolve({ items: [], next_step: null, generated_at: '' })
    }
    if (url.pathname === '/api/learning-path') {
      return Promise.resolve({ items: [], edges: [], stages: [], modules: [], path_summary: {} })
    }
    return Promise.resolve({})
  })
})

describe('Progress activity pagination', () => {
  it('loads first page then appends next activity page on "加载更多"', async () => {
    const { wrapper } = await mountAppWithRouter('/progress')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const activityCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/activity')
    expect(activityCalls.some((url) =>
      Number(url.searchParams.get('offset') || 0) === 0 && Number(url.searchParams.get('limit') || 0) === 30
    )).toBe(true)

    expect(wrapper.text()).toContain('已显示 30 / 35')
    expect(wrapper.text()).toContain('加载更多')

    const loadMoreBtn = wrapper.findAll('button').find((btn) => btn.text().includes('加载更多'))
    expect(loadMoreBtn).toBeTruthy()
    await loadMoreBtn.trigger('click')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const nextActivityCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/activity')
    expect(nextActivityCalls.some((url) => Number(url.searchParams.get('offset') || 0) === 30)).toBe(true)
    expect(wrapper.text()).toContain('已显示 35 / 35')
    expect(wrapper.text()).toContain('已显示全部')
    expect(wrapper.text()).toContain('动态 35')
  }, 20000)
})
