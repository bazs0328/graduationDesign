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
const kbFixtureTwo = { id: 'kb-2', name: '线性代数资料库' }
const REC_CACHE_KEY = (kbId = 'kb-1', userId = 'test') => `gradtutor_progress_rec_v3:${userId}:${kbId}`
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

function buildRecommendationPayload(docName = '网络推荐文档.pdf') {
  return {
    items: [
      {
        doc_id: `doc-${docName}`,
        doc_name: docName,
        status: 'on_track',
        completion_score: 46,
        urgency_score: 18,
        summary: `围绕 ${docName} 继续推进。`,
        actions: [
          {
            type: 'qa',
            reason: `围绕 ${docName} 做一次针对性提问。`,
            priority: 65,
          },
        ],
      },
    ],
    next_step: null,
    generated_at: new Date().toISOString(),
  }
}

function buildLearningPathItem(options = {}) {
  return {
    keypoint_id: options.keypoint_id || 'kp-1',
    text: options.text || '矩阵定义',
    doc_id: options.doc_id || 'doc-1',
    doc_name: options.doc_name || '矩阵.pdf',
    member_count: options.member_count ?? 1,
    source_doc_ids: options.source_doc_ids ?? ['doc-1'],
    source_doc_names: options.source_doc_names ?? ['矩阵.pdf'],
    mastery_level: options.mastery_level ?? 0.2,
    priority: options.priority ?? 'high',
    step: options.step ?? 1,
    prerequisites: options.prerequisites ?? [],
    prerequisite_ids: options.prerequisite_ids ?? [],
    unmet_prerequisite_ids: options.unmet_prerequisite_ids ?? [],
    is_unlocked: options.is_unlocked ?? true,
    action: options.action ?? 'study',
    stage: options.stage ?? 'foundation',
    module: options.module ?? 'module-1',
    difficulty: options.difficulty ?? 0.3,
    importance: options.importance ?? 0.8,
    path_level: options.path_level ?? 0,
    unlocks_count: options.unlocks_count ?? 0,
    estimated_time: options.estimated_time ?? 8,
    milestone: options.milestone ?? false,
  }
}

function buildLearningPathPayload(text = '矩阵定义', options = {}) {
  return {
    items: [
      buildLearningPathItem({
        keypoint_id: options.keypoint_id || `kp-${text}`,
        text,
        doc_id: options.doc_id || 'doc-1',
        doc_name: options.doc_name || '矩阵.pdf',
        member_count: options.member_count ?? 1,
        source_doc_ids: options.source_doc_ids ?? ['doc-1'],
        source_doc_names: options.source_doc_names ?? ['矩阵.pdf'],
        mastery_level: options.mastery_level ?? 0.2,
        priority: options.priority ?? 'high',
        step: options.step ?? 1,
        prerequisites: options.prerequisites ?? [],
        prerequisite_ids: options.prerequisite_ids ?? [],
        unmet_prerequisite_ids: options.unmet_prerequisite_ids ?? [],
        is_unlocked: options.is_unlocked ?? true,
        action: options.action ?? 'study',
        stage: options.stage ?? 'foundation',
        module: options.module ?? 'module-1',
        difficulty: options.difficulty ?? 0.3,
        importance: options.importance ?? 0.8,
        path_level: options.path_level ?? 0,
        unlocks_count: options.unlocks_count ?? 0,
        estimated_time: options.estimated_time ?? 8,
        milestone: options.milestone ?? false,
      }),
    ],
    edges: options.edges ?? [],
    stages: options.stages ?? [],
    modules: options.modules ?? [],
    path_summary: options.path_summary ?? {},
  }
}

function buildCacheEntry(payload, savedAt = Date.now()) {
  return JSON.stringify({
    version: 1,
    saved_at: savedAt,
    payload,
  })
}

function seedRecommendationCache(payload, options = {}) {
  const { kbId = 'kb-1', savedAt = Date.now() } = options
  localStorage.setItem(REC_CACHE_KEY(kbId), buildCacheEntry(payload, savedAt))
}

function seedLearningPathCache(payload, options = {}) {
  const { kbId = 'kb-1', savedAt = Date.now() } = options
  localStorage.setItem(PATH_CACHE_KEY(kbId), buildCacheEntry(payload, savedAt))
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
      return Promise.resolve(buildRecommendationPayload())
    }
    if (url.pathname === '/api/learning-path') {
      return Promise.resolve(buildLearningPathPayload('矩阵定义', {
        member_count: 2,
        source_doc_ids: ['doc-1', 'doc-2'],
        source_doc_names: ['矩阵.pdf', '线代讲义.pdf'],
        importance: 0.9,
        difficulty: 0.4,
        estimated_time: 10,
      }))
    }
    return Promise.resolve({})
  })
})

describe('Progress learning-path reuse', () => {
  it('loads recommendations and learning-path endpoints for Progress page render', async () => {
    await mountAppWithRouter('/progress')
    await waitForCondition(() => apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .some((url) => url.pathname === '/api/learning-path'))

    const recommendationCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/recommendations')
    const learningPathCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/learning-path')

    expect(recommendationCalls.length).toBeGreaterThan(0)
    expect(learningPathCalls.length).toBeGreaterThan(0)
  }, 40000)

  it('hydrates from persistent cache and still refreshes recommendations in background', async () => {
    seedRecommendationCache(buildRecommendationPayload('缓存推荐文档.pdf'))
    seedLearningPathCache({
      items: [
        buildLearningPathItem({
          keypoint_id: 'kp-unlocked',
          text: '矩阵定义',
          unlocks_count: 1,
        }),
        buildLearningPathItem({
          keypoint_id: 'kp-blocked',
          text: '特征值应用',
          step: 2,
          priority: 'high',
          action: 'quiz',
          stage: 'advanced',
          difficulty: 0.8,
          importance: 0.9,
          path_level: 1,
          estimated_time: 20,
          is_unlocked: false,
          prerequisite_ids: ['kp-unlocked'],
          unmet_prerequisite_ids: ['kp-unlocked'],
        }),
      ],
      edges: [{ from_id: 'kp-unlocked', to_id: 'kp-blocked', relation: 'prerequisite', confidence: 0.72 }],
      stages: [],
      modules: [],
      path_summary: {},
    })

    const { wrapper } = await mountAppWithRouter('/progress')
    await waitForCondition(() => apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .some((url) => url.pathname === '/api/learning-path'))

    const recommendationCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/recommendations')
    const learningPathCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/learning-path')

    expect(recommendationCalls.length).toBe(1)
    expect(learningPathCalls.length).toBe(1)
    expect(wrapper.text()).toContain('学习路径')
    expect(localStorage.getItem(REC_CACHE_KEY())).toBeTruthy()
    expect(localStorage.getItem(PATH_CACHE_KEY())).toBeTruthy()
  }, 40000)

  it('shows KB aggregation labels and source-doc count in learning path steps', async () => {
    const { wrapper } = await mountAppWithRouter('/progress')
    await waitForCondition(() => wrapper.html().includes('KB聚合'))

    const html = wrapper.html()
    expect(html).toContain('学习路径中的知识点已按资料库范围跨文档去重合并')
    expect(html).toContain('KB聚合')
    expect(html).toContain('来自 2 个文档')
  }, 40000)

  it('renders soft-stale cached recommendations and learning path while background refresh is pending', async () => {
    const baseApiGetImpl = apiGet.getMockImplementation()
    const pendingRecommendationsRefresh = new Promise(() => {})
    const pendingLearningPathRefresh = new Promise(() => {})
    const softStaleSavedAt = Date.now() - (31 * 60 * 1000)

    apiGet.mockImplementation((path) => {
      const url = parsePath(path)
      if (url.pathname === '/api/recommendations') {
        return pendingRecommendationsRefresh
      }
      if (url.pathname === '/api/learning-path') {
        return pendingLearningPathRefresh
      }
      return baseApiGetImpl ? baseApiGetImpl(path) : Promise.resolve({})
    })

    seedRecommendationCache(buildRecommendationPayload('缓存推荐卡片.pdf'), {
      savedAt: softStaleSavedAt,
    })
    seedLearningPathCache(buildLearningPathPayload('软过期缓存知识点'), {
      savedAt: softStaleSavedAt,
    })

    const { wrapper } = await mountAppWithRouter('/progress')
    await waitForCondition(() => (
      wrapper.text().includes('缓存推荐卡片.pdf')
      && wrapper.text().includes('软过期缓存知识点')
    ))

    expect(wrapper.text()).toContain('正在加载推荐...')
    expect(wrapper.text()).toContain('正在加载学习路径...')
  }, 40000)

  it('drops corrupted or hard-expired cache and falls back to fresh network data', async () => {
    const baseApiGetImpl = apiGet.getMockImplementation()
    const hardExpiredSavedAt = Date.now() - (8 * 24 * 60 * 60 * 1000)

    localStorage.setItem(REC_CACHE_KEY(), '{bad json')
    seedLearningPathCache(buildLearningPathPayload('过期缓存知识点'), {
      savedAt: hardExpiredSavedAt,
    })

    apiGet.mockImplementation((path) => {
      const url = parsePath(path)
      if (url.pathname === '/api/recommendations') {
        return Promise.resolve(buildRecommendationPayload('网络刷新推荐.pdf'))
      }
      if (url.pathname === '/api/learning-path') {
        return Promise.resolve(buildLearningPathPayload('网络刷新路径'))
      }
      return baseApiGetImpl ? baseApiGetImpl(path) : Promise.resolve({})
    })

    const { wrapper } = await mountAppWithRouter('/progress')
    await waitForCondition(() => (
      wrapper.text().includes('网络刷新推荐.pdf')
      && wrapper.text().includes('网络刷新路径')
    ))

    expect(wrapper.text()).not.toContain('过期缓存知识点')
    expect(localStorage.getItem(REC_CACHE_KEY())).not.toBe('{bad json')

    const savedRecommendationCache = JSON.parse(localStorage.getItem(REC_CACHE_KEY()))
    const savedLearningPathCache = JSON.parse(localStorage.getItem(PATH_CACHE_KEY()))

    expect(savedRecommendationCache.payload.items[0].doc_name).toBe('网络刷新推荐.pdf')
    expect(savedLearningPathCache.payload.items[0].text).toBe('网络刷新路径')
  }, 40000)

  it('hydrates cached content immediately when switching to another KB', async () => {
    const pendingRecommendationsRefresh = new Promise(() => {})
    const pendingLearningPathRefresh = new Promise(() => {})

    seedRecommendationCache(buildRecommendationPayload('缓存推荐 KB2.pdf'), {
      kbId: 'kb-2',
    })
    seedLearningPathCache(buildLearningPathPayload('缓存路径 KB2'), {
      kbId: 'kb-2',
    })

    apiGet.mockImplementation((path) => {
      const url = parsePath(path)
      if (url.pathname === '/api/kb') {
        return Promise.resolve([kbFixture, kbFixtureTwo])
      }
      if (url.pathname === '/api/progress') {
        return Promise.resolve(buildProgressPayload())
      }
      if (url.pathname === '/api/activity') {
        return Promise.resolve(buildActivityPayload())
      }
      if (url.pathname === '/api/recommendations') {
        if (url.searchParams.get('kb_id') === 'kb-2') {
          return pendingRecommendationsRefresh
        }
        return Promise.resolve(buildRecommendationPayload('KB1 网络推荐.pdf'))
      }
      if (url.pathname === '/api/learning-path') {
        if (url.searchParams.get('kb_id') === 'kb-2') {
          return pendingLearningPathRefresh
        }
        return Promise.resolve(buildLearningPathPayload('KB1 网络路径'))
      }
      return Promise.resolve({})
    })

    const { wrapper } = await mountAppWithRouter('/progress')
    await waitForCondition(() => wrapper.find('select').exists())
    await wrapper.find('select').setValue('kb-2')
    await waitForCondition(() => (
      wrapper.text().includes('缓存推荐 KB2.pdf')
      && wrapper.text().includes('缓存路径 KB2')
    ))

    expect(wrapper.text()).toContain('正在加载推荐...')
    expect(wrapper.text()).toContain('正在加载学习路径...')
  }, 40000)

  it('routes blocked learning-path items to the first unmet prerequisite action instead of always opening QA', async () => {
    const baseApiGetImpl = apiGet.getMockImplementation()
    apiGet.mockImplementation((path) => {
      const url = parsePath(path)
      if (url.pathname === '/api/recommendations') {
        return Promise.resolve({
          items: [],
          next_step: null,
          generated_at: '',
        })
      }
      if (url.pathname === '/api/learning-path') {
        return Promise.resolve({
          items: [
            buildLearningPathItem({
              keypoint_id: 'kp-unlocked',
              text: '矩阵定义',
              action: 'quiz',
            }),
            buildLearningPathItem({
              keypoint_id: 'kp-blocked',
              text: '特征值应用',
              step: 2,
              action: 'study',
              stage: 'advanced',
              difficulty: 0.8,
              importance: 0.9,
              path_level: 1,
              estimated_time: 20,
              is_unlocked: false,
              prerequisite_ids: ['kp-unlocked'],
              unmet_prerequisite_ids: ['kp-unlocked'],
            }),
          ],
          edges: [{ from_id: 'kp-unlocked', to_id: 'kp-blocked', relation: 'prerequisite', confidence: 0.72 }],
          stages: [],
          modules: [],
          path_summary: {},
        })
      }
      return baseApiGetImpl ? baseApiGetImpl(path) : Promise.resolve({})
    })

    const { wrapper, router } = await mountAppWithRouter('/progress')
    await waitForCondition(() => wrapper.text().includes('先学前置'))

    const blockedActionButton = wrapper
      .findAll('button')
      .find((btn) => btn.text().includes('先学前置'))

    expect(blockedActionButton).toBeTruthy()
    await blockedActionButton.trigger('click')
    await flushPromises()
    await nextTick()

    await waitForCondition(() => router.currentRoute.value.path === '/quiz')
    expect(router.currentRoute.value.path).toBe('/quiz')
    expect(router.currentRoute.value.query.kb_id).toBe('kb-1')
    expect(router.currentRoute.value.query.doc_id).toBe('doc-1')
    expect(router.currentRoute.value.query.focus).toBe('矩阵定义')
  }, 40000)
})
