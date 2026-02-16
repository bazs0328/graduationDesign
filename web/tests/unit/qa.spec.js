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

const kbFixture = { id: 'kb-1', name: 'Default' }
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

const qaResponse = {
  answer: 'A matrix is a rectangular array of numbers.',
  sources: [{ source: 'doc p.1 c.0', snippet: 'Matrix definition...' }]
}

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

async function mountAppWithRouter() {
  localStorage.setItem('gradtutor_user_id', 'test')
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
    if (path.startsWith('/api/recommendations')) return Promise.resolve({ items: [] })
    return Promise.resolve({})
  })

  apiPost.mockImplementation((path) => {
    if (path === '/api/qa') return Promise.resolve(qaResponse)
    return Promise.resolve({})
  })
})

describe('Q&A', () => {
  it('sends kb_id and question on Ask', async () => {
    const { wrapper, router } = await mountAppWithRouter()

    await router.push('/qa')
    await flushPromises()
    await nextTick()
    await nextTick()

    const kbSelect = wrapper.find('select')
    expect(kbSelect.exists()).toBe(true)
    await kbSelect.setValue('kb-1')
    await flushPromises()
    await nextTick()

    const textarea = wrapper.find('textarea')
    await textarea.setValue('What is a matrix?')
    await nextTick()

    const inputContainer = wrapper.find('textarea').element.closest('div')
    const sendBtnEl = inputContainer?.querySelector('button')
    expect(sendBtnEl).toBeTruthy()
    sendBtnEl?.click()
    await flushPromises()
    await nextTick()

    expect(apiPost).toHaveBeenCalledWith(
      '/api/qa',
      expect.objectContaining({
        kb_id: 'kb-1',
        question: 'What is a matrix?'
      })
    )
  })

  it('renders answer and sources in qa-log', async () => {
    const { wrapper, router } = await mountAppWithRouter()

    await router.push('/qa')
    await flushPromises()
    await nextTick()
    await nextTick()

    const kbSelect = wrapper.find('select')
    expect(kbSelect.exists()).toBe(true)
    await kbSelect.setValue('kb-1')
    await flushPromises()
    await nextTick()

    await wrapper.find('textarea').setValue('What is a matrix?')
    await nextTick()
    const inputContainer = wrapper.find('textarea').element.closest('div')
    const sendBtnEl = inputContainer?.querySelector('button')
    sendBtnEl?.click()
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    expect(html).toContain(qaResponse.answer)
    expect(html).toContain('doc p.1 c.0')
  })
})
