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

async function waitForCondition(predicate, options = {}) {
  const { timeoutMs = 30000, intervalMs = 20 } = options
  const start = Date.now()
  while (Date.now() - start <= timeoutMs) {
    await flushPromises()
    await nextTick()
    if (predicate()) return
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  throw new Error('Timed out waiting for condition')
}

function parsePath(path) {
  return new URL(path, 'http://localhost')
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function buildRecommendationsPayload(keypointText) {
  return {
    items: [],
    next_step: null,
    generated_at: new Date().toISOString(),
    learning_path: [
      {
        keypoint_id: `kp-${keypointText}`,
        text: keypointText,
        doc_id: 'doc-1',
        doc_name: '矩阵.pdf',
        member_count: 1,
        source_doc_ids: ['doc-1'],
        source_doc_names: ['矩阵.pdf'],
        mastery_level: 0.2,
        priority: 'high',
        step: 1,
        prerequisites: [],
        action: 'study',
        stage: 'foundation',
        module: 'module-1',
        difficulty: 0.4,
        importance: 0.9,
        estimated_time: 10,
        milestone: false,
      },
    ],
    learning_path_edges: [],
    learning_path_stages: [],
    learning_path_modules: [],
    learning_path_summary: {
      total_items: 1,
      completed_items: 0,
      completion_rate: 0,
      total_estimated_time: 10,
      stages_count: 1,
      modules_count: 1,
      current_stage: 'foundation',
      current_stage_label: '基础阶段',
      ability_level: 'intermediate',
    },
  }
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
  sessionStorage.clear()

  getProfile.mockResolvedValue({ ability_level: 'intermediate' })
  buildLearningPath.mockResolvedValue({})
  apiPost.mockResolvedValue({})
})

describe('Progress revisit background refresh', () => {
  it('keeps previous learning-path content visible and shows refresh indicator when revisiting Progress', async () => {
    const secondRecommendations = deferred()
    let recommendationCallCount = 0

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
        return Promise.resolve({
          items: [],
          total: 0,
          offset: 0,
          limit: 30,
          has_more: false,
        })
      }
      if (url.pathname === '/api/recommendations') {
        recommendationCallCount += 1
        if (recommendationCallCount === 1) {
          return Promise.resolve(buildRecommendationsPayload('首轮知识点'))
        }
        if (recommendationCallCount === 2) {
          return secondRecommendations.promise
        }
        return Promise.resolve(buildRecommendationsPayload('回访刷新后知识点'))
      }
      if (url.pathname === '/api/learning-path') {
        return Promise.resolve({ items: [], edges: [], stages: [], modules: [], path_summary: {} })
      }
      return Promise.resolve({})
    })

    const { wrapper, router } = await mountAppWithRouter('/progress')
    await waitForCondition(() => wrapper.text().includes('首轮知识点'))

    await router.push('/')
    await flushPromises()
    await nextTick()

    await router.push('/progress')
    await waitForCondition(
      () => recommendationCallCount === 2
        && wrapper.text().includes('首轮知识点')
        && wrapper.text().includes('正在加载推荐...'),
    )

    expect(recommendationCallCount).toBe(2)
    expect(wrapper.text()).toContain('首轮知识点')
    expect(wrapper.text()).toContain('正在加载推荐...')

    secondRecommendations.resolve(buildRecommendationsPayload('回访刷新后知识点'))
    await waitForCondition(() => wrapper.text().includes('回访刷新后知识点'))

    expect(wrapper.text()).toContain('回访刷新后知识点')

    const learningPathCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/learning-path')
    expect(learningPathCalls.length).toBe(0)
  }, 30000)
})
