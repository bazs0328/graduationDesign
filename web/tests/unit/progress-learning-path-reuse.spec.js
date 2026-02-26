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
      return Promise.resolve({
        items: [],
        next_step: null,
        generated_at: '',
        learning_path: [
          {
            keypoint_id: 'kp-1',
            text: '矩阵定义',
            doc_id: 'doc-1',
            doc_name: '矩阵.pdf',
            member_count: 2,
            source_doc_ids: ['doc-1', 'doc-2'],
            source_doc_names: ['矩阵.pdf', '线代讲义.pdf'],
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
        learning_path_stages: [
          {
            stage_id: 'foundation',
            name: '基础阶段',
            description: 'desc',
            keypoint_ids: ['kp-1'],
            milestone_keypoint_id: null,
            estimated_time: 10,
          },
        ],
        learning_path_modules: [
          {
            module_id: 'module-1',
            name: '模块1',
            description: 'desc',
            keypoint_ids: ['kp-1'],
            prerequisite_modules: [],
            estimated_time: 10,
          },
        ],
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
      })
    }
    if (url.pathname === '/api/learning-path') {
      return Promise.resolve({ items: [], edges: [], stages: [], modules: [], path_summary: {} })
    }
    return Promise.resolve({})
  })
})

describe('Progress learning-path reuse', () => {
  it('reuses learning path from recommendations response without extra /api/learning-path request', async () => {
    await mountAppWithRouter('/progress')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const recommendationCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/recommendations')
    const learningPathCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/learning-path')

    expect(recommendationCalls.length).toBeGreaterThan(0)
    expect(learningPathCalls.length).toBe(0)
  }, 20000)

  it('hydrates recommendations and learning path from session cache on remount without manual reload', async () => {
    localStorage.setItem(
      'gradtutor_app_ctx_v1:test',
      JSON.stringify({ selectedKbId: 'kb-1', selectedDocId: '' }),
    )
    sessionStorage.setItem(
      'gradtutor_progress_rec_v1:test:kb-1',
      JSON.stringify({
        saved_at: Date.now(),
        payload: {
          items: [],
          next_step: null,
          generated_at: '',
          learning_path: [
            {
              keypoint_id: 'kp-cache-1',
              text: '缓存知识点',
              doc_id: 'doc-1',
              doc_name: '缓存文档.pdf',
              member_count: 1,
              source_doc_ids: [],
              source_doc_names: [],
              mastery_level: 0.1,
              priority: 'high',
              step: 1,
              prerequisites: [],
              action: 'study',
              stage: 'foundation',
              module: 'module-1',
              difficulty: 0.3,
              importance: 0.8,
              estimated_time: 8,
              milestone: false,
            },
          ],
          learning_path_edges: [],
          learning_path_stages: [],
          learning_path_modules: [],
          learning_path_summary: {},
        },
      }),
    )

    const { wrapper } = await mountAppWithRouter('/progress')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const recommendationCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/recommendations')
    const learningPathCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/learning-path')

    expect(recommendationCalls.length).toBe(0)
    expect(learningPathCalls.length).toBe(0)
    expect(wrapper.text()).toContain('缓存知识点')
  }, 20000)

  it('shows KB aggregation labels and source-doc count in learning path steps', async () => {
    localStorage.setItem(
      'gradtutor_app_ctx_v1:test',
      JSON.stringify({ selectedKbId: 'kb-1', selectedDocId: '' }),
    )
    sessionStorage.setItem(
      'gradtutor_progress_rec_v1:test:kb-1',
      JSON.stringify({
        saved_at: Date.now(),
        payload: {
          items: [],
          next_step: null,
          generated_at: '',
          learning_path: [
            {
              keypoint_id: 'kp-agg-1',
              text: '矩阵定义',
              doc_id: 'doc-1',
              doc_name: '矩阵.pdf',
              member_count: 2,
              source_doc_ids: ['doc-1', 'doc-2'],
              source_doc_names: ['矩阵.pdf', '线代讲义.pdf'],
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
          learning_path_summary: {},
        },
      }),
    )

    const { wrapper } = await mountAppWithRouter('/progress')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    expect(html).toContain('学习路径中的知识点已按知识库跨文档去重合并')
    expect(html).toContain('KB聚合')
    expect(html).toContain('来自 2 个文档')
  }, 20000)

  it('renders unlocked queue and blocked prerequisite hints from learning path metadata', async () => {
    localStorage.setItem(
      'gradtutor_app_ctx_v1:test',
      JSON.stringify({ selectedKbId: 'kb-1', selectedDocId: '' }),
    )
    sessionStorage.setItem(
      'gradtutor_progress_rec_v1:test:kb-1',
      JSON.stringify({
        saved_at: Date.now(),
        payload: {
          items: [],
          next_step: null,
          generated_at: '',
          learning_path: [
            {
              keypoint_id: 'kp-unlocked',
              text: '矩阵定义',
              doc_id: 'doc-1',
              doc_name: '矩阵.pdf',
              mastery_level: 0.1,
              priority: 'high',
              step: 1,
              prerequisites: [],
              prerequisite_ids: [],
              unmet_prerequisite_ids: [],
              is_unlocked: true,
              action: 'study',
              stage: 'foundation',
              module: 'module-1',
              difficulty: 0.2,
              importance: 0.8,
              path_level: 0,
              unlocks_count: 1,
              estimated_time: 8,
              milestone: false,
              member_count: 1,
              source_doc_ids: [],
              source_doc_names: [],
            },
            {
              keypoint_id: 'kp-blocked',
              text: '特征值应用',
              doc_id: 'doc-1',
              doc_name: '矩阵.pdf',
              mastery_level: 0.0,
              priority: 'high',
              step: 2,
              prerequisites: [],
              prerequisite_ids: ['kp-unlocked'],
              unmet_prerequisite_ids: ['kp-unlocked'],
              is_unlocked: false,
              action: 'quiz',
              stage: 'advanced',
              module: 'module-1',
              difficulty: 0.8,
              importance: 0.9,
              path_level: 1,
              unlocks_count: 0,
              estimated_time: 20,
              milestone: false,
              member_count: 1,
              source_doc_ids: [],
              source_doc_names: [],
            },
          ],
          learning_path_edges: [
            { from_id: 'kp-unlocked', to_id: 'kp-blocked', relation: 'prerequisite', confidence: 0.72 },
          ],
          learning_path_stages: [],
          learning_path_modules: [],
          learning_path_summary: {},
        },
      }),
    )

    const { wrapper } = await mountAppWithRouter('/progress')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    expect(html).toContain('当前可学队列')
    expect(html).toContain('当前可学')
    expect(html).toContain('阻塞')
    expect(html).toContain('缺少前置')
    expect(html).toContain('矩阵定义')
  }, 20000)
})
