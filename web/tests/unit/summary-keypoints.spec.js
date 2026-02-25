import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

import App from '@/App.vue'
import { routes } from '@/router'
import { apiGet, apiPost } from '@/api'

vi.mock('@/api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    apiGet: vi.fn(),
    apiPost: vi.fn()
  }
})

const docFixture = {
  id: 'doc-1',
  user_id: 'user_test',
  kb_id: 'kb-1',
  filename: 'sample.txt',
  file_type: 'txt',
  num_chunks: 1,
  num_pages: 1,
  char_count: 10,
  status: 'ready',
  created_at: new Date().toISOString()
}

const kbFixture = { id: 'kb-1', name: 'Default' }

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

async function mountAppWithRouter() {
  localStorage.setItem('gradtutor_user_id', 'test')
  localStorage.setItem('gradtutor_user', 'test')
  localStorage.setItem('gradtutor_access_token', 'test-token')
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(App, {
    global: {
      plugins: [pinia, router]
    }
  })
  await flushPromises()
  await nextTick()
  return { wrapper, router }
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  localStorage.clear()

  apiGet.mockImplementation((path) => {
    if (path.startsWith('/api/kb')) return Promise.resolve([kbFixture])
    if (path.startsWith('/api/docs')) return Promise.resolve([docFixture])
    if (path.startsWith('/api/keypoints/kb/')) {
      return Promise.resolve({
        grouped: true,
        raw_count: 3,
        group_count: 2,
        keypoints: [
          {
            id: 'kp-group-1',
            text: '矩阵定义',
            explanation: '矩阵是按行列排列的数表。',
            member_count: 2,
            source_doc_ids: ['doc-1', 'doc-2'],
            source_doc_names: ['矩阵.pdf', '线代讲义.pdf'],
            source_refs: [
              { keypoint_id: 'kp-a', doc_id: 'doc-1', doc_name: '矩阵.pdf', page: 1, chunk: 0 },
              { keypoint_id: 'kp-b', doc_id: 'doc-2', doc_name: '线代讲义.pdf', page: 2, chunk: 1 }
            ]
          },
          {
            id: 'kp-group-2',
            text: '特征值',
            member_count: 1,
            source_doc_ids: ['doc-1'],
            source_doc_names: ['矩阵.pdf'],
            source_refs: [{ keypoint_id: 'kp-c', doc_id: 'doc-1', doc_name: '矩阵.pdf', page: 3 }]
          }
        ]
      })
    }
    if (path.startsWith('/api/progress')) {
      return Promise.resolve({
        total_docs: 1,
        total_quizzes: 0,
        total_attempts: 0,
        total_questions: 0,
        total_summaries: 0,
        total_keypoints: 0,
        avg_score: 0,
        last_activity: null
      })
    }
    if (path.startsWith('/api/activity')) return Promise.resolve({ items: [] })
    return Promise.resolve({})
  })

  apiPost.mockImplementation((path) => {
    if (path === '/api/summary') return Promise.resolve({ summary: 'ok', cached: false })
    if (path === '/api/keypoints') {
      return Promise.resolve({
        keypoints: [{ text: 'k1', explanation: 'explanation for k1', page: 1 }],
        cached: false
      })
    }
    return Promise.resolve({})
  })
})

describe('Summary/Keypoints payloads', () => {
  it('sends boolean force on summarize', async () => {
    const { wrapper, router } = await mountAppWithRouter()

    await router.push('/summary')
    await flushPromises()
    await nextTick()
    await nextTick()

    const docSelect = wrapper.find('select')
    expect(docSelect.exists()).toBe(true)
    await docSelect.setValue('doc-1')
    await nextTick()

    const summarizeBtn = wrapper
      .findAll('button')
      .find((btn) => btn.text().includes('生成摘要'))
    expect(summarizeBtn).toBeTruthy()
    await summarizeBtn.trigger('click')

    expect(apiPost).toHaveBeenCalledWith(
      '/api/summary',
      expect.objectContaining({ force: false })
    )
  })

  it('sends boolean force on keypoints', async () => {
    const { wrapper, router } = await mountAppWithRouter()

    await router.push('/summary')
    await flushPromises()
    await nextTick()
    await nextTick()

    const docSelect = wrapper.find('select')
    expect(docSelect.exists()).toBe(true)
    await docSelect.setValue('doc-1')
    await nextTick()

    const keypointsBtn = wrapper
      .findAll('button')
      .find((btn) => btn.text().includes('提取要点'))
    expect(keypointsBtn).toBeTruthy()
    await keypointsBtn.trigger('click')

    expect(apiPost).toHaveBeenCalledWith(
      '/api/keypoints',
      expect.objectContaining({ force: false })
    )
  })

  it('renders keypoints with text, explanation, and source', async () => {
    const { wrapper, router } = await mountAppWithRouter()

    await router.push('/summary')
    await flushPromises()
    await nextTick()
    await nextTick()

    const docSelect = wrapper.find('select')
    expect(docSelect.exists()).toBe(true)
    await docSelect.setValue('doc-1')
    await nextTick()

    const keypointsBtn = wrapper
      .findAll('button')
      .find((btn) => btn.text().includes('提取要点'))
    await keypointsBtn.trigger('click')
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    expect(html).toContain('k1')
    expect(html).toContain('explanation for k1')
    expect(html).toContain('p.1')
    expect(html).toContain('单文档视图')
    expect(html).toContain('当前展示的是该文档提取结果')
    expect(html).toContain('查看 KB 学习路径')
  })

  it('loads and renders kb grouped keypoints panel on demand', async () => {
    const { wrapper, router } = await mountAppWithRouter()

    await router.push('/summary')
    await flushPromises()
    await nextTick()
    await nextTick()

    const docSelect = wrapper.find('select')
    await docSelect.setValue('doc-1')
    await nextTick()

    const keypointsBtn = wrapper
      .findAll('button')
      .find((btn) => btn.text().includes('提取要点'))
    await keypointsBtn.trigger('click')
    await flushPromises()
    await nextTick()

    const groupedBtn = wrapper
      .findAll('button')
      .find((btn) => btn.text().includes('查看知识库聚合知识点'))
    expect(groupedBtn).toBeTruthy()
    await groupedBtn.trigger('click')
    await flushPromises()
    await nextTick()

    expect(apiGet).toHaveBeenCalledWith(
      expect.stringContaining('/api/keypoints/kb/kb-1?')
    )
    const groupedCall = apiGet.mock.calls.find(([path]) => path.includes('/api/keypoints/kb/kb-1?'))
    expect(groupedCall?.[0]).toContain('grouped=true')
    expect(groupedCall?.[0]).toContain('user_id=test')

    const html = wrapper.html()
    expect(html).toContain('知识库聚合视图')
    expect(html).toContain('聚合后 2 项')
    expect(html).toContain('原始 3 项')
    expect(html).toContain('矩阵定义')
    expect(html).toContain('KB聚合')
    expect(html).toContain('来自 2 个文档')
    expect(html).toContain('矩阵.pdf')
    expect(html).toContain('线代讲义.pdf')
    expect(html).toContain('查看来源定位（2）')
  })
})
