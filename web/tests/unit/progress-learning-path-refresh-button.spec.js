import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

import App from '@/App.vue'
import { routes } from '@/router'
import {
  apiGet,
  apiPost,
  buildLearningPath,
  getProfile,
  getSettings,
  authMe,
  getSystemProviderSettings,
  getSystemSettings,
} from '@/api'
import {
  buildProviderConfigResponse,
  buildSettingsResponse,
  buildSystemSettingsResponse,
} from './fixtures/settingsFixtures'

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
    getSettings: vi.fn(),
    authMe: vi.fn(),
    getSystemSettings: vi.fn(),
    getSystemProviderSettings: vi.fn(),
  }
})

const kbFixture = { id: 'kb-1', name: '默认知识库' }
const PATH_CACHE_KEY = (kbId = 'kb-1', userId = 'test') => `gradtutor_progress_path_v2:${userId}:${kbId}`

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

async function waitForCondition(predicate, options = {}) {
  const { timeoutMs = 20000, intervalMs = 20 } = options
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

function buildProgressPayload() {
  return {
    total_docs: 1,
    total_quizzes: 0,
    total_attempts: 0,
    total_questions: 0,
    total_summaries: 0,
    total_keypoints: 0,
    avg_score: 0,
    last_activity: null,
    by_kb: [],
  }
}

function buildActivityPayload() {
  return {
    items: [],
    total: 0,
    offset: 0,
    limit: 30,
    has_more: false,
  }
}

function buildLearningPathPayload(text = '矩阵定义') {
  return {
    items: [
      {
        keypoint_id: `kp-${text}`,
        text,
        doc_id: 'doc-1',
        doc_name: '矩阵.pdf',
        mastery_level: 0.2,
        priority: 'high',
        step: 1,
        prerequisites: [],
        prerequisite_ids: [],
        unmet_prerequisite_ids: [],
        is_unlocked: true,
        action: 'study',
        stage: 'foundation',
        module: 'module-1',
        difficulty: 0.3,
        importance: 0.8,
        path_level: 0,
        unlocks_count: 0,
        estimated_time: 8,
        milestone: false,
        member_count: 1,
        source_doc_ids: ['doc-1'],
        source_doc_names: ['矩阵.pdf'],
      },
    ],
    edges: [],
    stages: [],
    modules: [],
    path_summary: {},
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
  return { wrapper }
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  getProfile.mockReset()
  buildLearningPath.mockReset()
  getSettings.mockReset()
  authMe.mockReset()
  getSystemSettings.mockReset()
  getSystemProviderSettings.mockReset()
  localStorage.clear()
  sessionStorage.clear()

  localStorage.setItem(
    'gradtutor_app_ctx_v1:test',
    JSON.stringify({ selectedKbId: 'kb-1', selectedDocId: '' }),
  )

  getProfile.mockResolvedValue({ ability_level: 'intermediate' })
  buildLearningPath.mockResolvedValue({})
  apiPost.mockResolvedValue({})
  getSettings.mockResolvedValue(buildSettingsResponse())
  authMe.mockResolvedValue({ user_id: 'test', username: 'test', name: 'test', access_token: 'test-token' })
  getSystemSettings.mockResolvedValue(buildSystemSettingsResponse())
  getSystemProviderSettings.mockResolvedValue(buildProviderConfigResponse())

  apiGet.mockImplementation((path) => {
    const url = parsePath(path)
    if (url.pathname === '/api/kb') {
      return Promise.resolve([kbFixture])
    }
    if (url.pathname === '/api/progress') {
      return Promise.resolve(buildProgressPayload())
    }
    if (url.pathname === '/api/activity') {
      return Promise.resolve(buildActivityPayload())
    }
    if (url.pathname === '/api/recommendations') {
      return Promise.resolve({
        items: [],
        next_step: null,
        generated_at: '',
        learning_path: [],
        learning_path_edges: [],
        learning_path_stages: [],
        learning_path_modules: [],
        learning_path_summary: {},
      })
    }
    if (url.pathname === '/api/learning-path') {
      return Promise.resolve(buildLearningPathPayload())
    }
    return Promise.resolve({})
  })
})

describe('Progress learning-path refresh button', () => {
  it('refreshes via /api/learning-path, writes back local cache, and does not call force build API', async () => {
    let learningPathCallCount = 0
    const baseApiGetImpl = apiGet.getMockImplementation()
    apiGet.mockImplementation((path) => {
      const url = parsePath(path)
      if (url.pathname === '/api/learning-path') {
        learningPathCallCount += 1
        if (learningPathCallCount === 1) {
          return Promise.resolve(buildLearningPathPayload('首轮路径'))
        }
        return Promise.resolve(buildLearningPathPayload('刷新后路径'))
      }
      return baseApiGetImpl ? baseApiGetImpl(path) : Promise.resolve({})
    })

    const { wrapper } = await mountAppWithRouter('/progress')
    await waitForCondition(() => wrapper.text().includes('首轮路径'))
    await waitForCondition(() => {
      const cached = localStorage.getItem(PATH_CACHE_KEY())
      return Boolean(cached) && JSON.parse(cached).payload.items[0].text === '首轮路径'
    })

    const beforeCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/learning-path').length

    const refreshButton = wrapper.find('button[aria-label="刷新学习路径"]')
    expect(refreshButton.exists()).toBe(true)
    await refreshButton.trigger('click')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const afterCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/learning-path').length

    expect(buildLearningPath).not.toHaveBeenCalled()
    expect(afterCalls).toBe(beforeCalls + 1)

    await waitForCondition(() => {
      const cached = localStorage.getItem(PATH_CACHE_KEY())
      return Boolean(cached) && JSON.parse(cached).payload.items[0].text === '刷新后路径'
    })

    const savedCache = JSON.parse(localStorage.getItem(PATH_CACHE_KEY()))
    expect(savedCache.payload.items[0].text).toBe('刷新后路径')
  }, 40000)
})
