import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
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
  localStorage.setItem('gradtutor_access_token', 'test-token')
  const router = createRouter({
    history: createMemoryHistory(),
    routes
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(App, {
    global: {
      plugins: [router]
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
  })
})
