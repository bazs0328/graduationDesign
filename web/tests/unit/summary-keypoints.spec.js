import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import App from '@/App.vue'
import { apiGet, apiPost } from '@/api'

vi.mock('@/api', () => ({
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

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()

  apiGet.mockImplementation((path) => {
    if (path.startsWith('/api/kb')) {
      return Promise.resolve([])
    }
    if (path.startsWith('/api/docs')) {
      return Promise.resolve([docFixture])
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
    if (path.startsWith('/api/activity')) {
      return Promise.resolve({ items: [] })
    }
    return Promise.resolve({})
  })

  apiPost.mockImplementation((path) => {
    if (path === '/api/summary') {
      return Promise.resolve({ summary: 'ok', cached: false })
    }
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
    const wrapper = mount(App)
    await flushPromises()
    await nextTick()

    const summaryTab = wrapper.findAll('button').find((btn) => btn.text() === 'Summary')
    expect(summaryTab).toBeTruthy()
    await summaryTab.trigger('click')
    await nextTick()

    const summarizeBtn = wrapper
      .findAll('button')
      .find((btn) => btn.text().toLowerCase().includes('summarize'))
    expect(summarizeBtn).toBeTruthy()
    await summarizeBtn.trigger('click')

    expect(apiPost).toHaveBeenCalledWith(
      '/api/summary',
      expect.objectContaining({ force: false })
    )
  })

  it('sends boolean force on keypoints', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await nextTick()

    const summaryTab = wrapper.findAll('button').find((btn) => btn.text() === 'Summary')
    expect(summaryTab).toBeTruthy()
    await summaryTab.trigger('click')
    await nextTick()

    const keypointsBtn = wrapper
      .findAll('button')
      .find((btn) => btn.text().toLowerCase().includes('extract keypoints'))
    expect(keypointsBtn).toBeTruthy()
    await keypointsBtn.trigger('click')

    expect(apiPost).toHaveBeenCalledWith(
      '/api/keypoints',
      expect.objectContaining({ force: false })
    )
  })

  it('renders keypoints with text, explanation, and source', async () => {
    const wrapper = mount(App)
    await flushPromises()
    await nextTick()

    const summaryTab = wrapper.findAll('button').find((btn) => btn.text() === 'Summary')
    await summaryTab.trigger('click')
    await nextTick()

    const keypointsBtn = wrapper
      .findAll('button')
      .find((btn) => btn.text().toLowerCase().includes('extract keypoints'))
    await keypointsBtn.trigger('click')
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    expect(html).toContain('k1')
    expect(html).toContain('explanation for k1')
    expect(html).toContain('p.1')
  })
})
