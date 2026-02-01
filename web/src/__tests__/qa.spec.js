import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import App from '../App.vue'
import { apiGet, apiPost } from '../api'

vi.mock('../api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn()
}))

const docFixture = {
  id: 'doc-1',
  user_id: 'user_test',
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

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()

  apiGet.mockImplementation((path) => {
    if (path.startsWith('/api/kb')) return Promise.resolve([])
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

  apiPost.mockImplementation((path, body) => {
    if (path === '/api/qa') return Promise.resolve(qaResponse)
    return Promise.resolve({})
  })
})

describe('Q&A', () => {
  it('sends doc_id and question on Ask', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await nextTick()

    const qaTab = wrapper.findAll('button').find((btn) => btn.text() === 'Q&A')
    expect(qaTab).toBeTruthy()
    await qaTab.trigger('click')
    await nextTick()

    const select = wrapper.find('select')
    await select.setValue('doc-1')
    await nextTick()

    const textarea = wrapper.find('textarea')
    await textarea.setValue('What is a matrix?')
    await nextTick()

    const askBtn = wrapper.findAll('button').find((btn) => btn.text() === 'Ask')
    expect(askBtn).toBeTruthy()
    await askBtn.trigger('click')
    await flushPromises()
    await nextTick()

    expect(apiPost).toHaveBeenCalledWith(
      '/api/qa',
      expect.objectContaining({
        doc_id: 'doc-1',
        question: 'What is a matrix?'
      })
    )
  })

  it('renders answer and sources in qa-log', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await nextTick()

    const qaTab = wrapper.findAll('button').find((btn) => btn.text() === 'Q&A')
    await qaTab.trigger('click')
    await nextTick()

    await wrapper.find('select').setValue('doc-1')
    await nextTick()
    await wrapper.find('textarea').setValue('What is a matrix?')
    await nextTick()

    const askBtn = wrapper.findAll('button').find((btn) => btn.text() === 'Ask')
    await askBtn.trigger('click')
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    expect(html).toContain(qaResponse.answer)
    expect(html).toContain('doc p.1 c.0')
  })
})
