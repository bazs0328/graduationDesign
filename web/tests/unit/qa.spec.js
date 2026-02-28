import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

import App from '@/App.vue'
import { routes } from '@/router'
import { apiGet, apiPost, apiSsePost, getDifficultyPlan, getProfile } from '@/api'

vi.mock('@/api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    apiSsePost: vi.fn(),
    getProfile: vi.fn(),
    getDifficultyPlan: vi.fn(),
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
  sources: [{ source: 'doc p.1 c.0', snippet: 'Matrix definition...' }],
  mode: 'normal'
}
const profileResponse = {
  ability_level: 'intermediate',
  recent_accuracy: 0.62,
  frustration_score: 0.32,
  total_attempts: 8,
  weak_concepts: ['矩阵乘法', '特征值', '向量空间'],
}
const difficultyPlanResponse = {
  easy: 0.3,
  medium: 0.5,
  hard: 0.2,
}
const explainAnswer = [
  '## 题意理解',
  '这是在问矩阵的基本定义。',
  '## 相关知识点',
  '- 矩阵',
  '- 行与列',
  '## 分步解答',
  '矩阵是按行列排列的数表。',
  '## 易错点',
  '不要把矩阵和行向量混淆。',
  '## 自测问题',
  '2x3 矩阵有几行几列？'
].join('\n')

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
  apiSsePost.mockReset()
  getProfile.mockReset()
  getDifficultyPlan.mockReset()
  localStorage.clear()

  apiGet.mockImplementation((path) => {
    if (path.startsWith('/api/kb')) return Promise.resolve([kbFixture])
    if (path.startsWith('/api/docs')) return Promise.resolve([docFixture])
    if (path.startsWith('/api/chat/sessions/page')) {
      return Promise.resolve({
        items: [
          {
            id: 'session-qa-1',
            title: 'What is a matrix?',
            kb_id: 'kb-1',
            doc_id: null,
            created_at: new Date().toISOString(),
          }
        ],
        total: 1,
        offset: 0,
        limit: 20,
        has_more: false,
      })
    }
    if (path.startsWith('/api/chat/sessions/session-qa-1/messages')) {
      return Promise.resolve([
        { role: 'user', content: 'What is a matrix?' },
        { role: 'assistant', content: qaResponse.answer, sources: qaResponse.sources }
      ])
    }
    if (path.startsWith('/api/chat/sessions/')) return Promise.resolve([])
    if (path.startsWith('/api/chat/sessions')) {
      return Promise.resolve([
        { id: 'session-qa-1', title: 'What is a matrix?', kb_id: 'kb-1', doc_id: null }
      ])
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
    if (path.startsWith('/api/activity')) return Promise.resolve({ items: [], total: 0, offset: 0, limit: 30, has_more: false })
    if (path.startsWith('/api/recommendations')) return Promise.resolve({ items: [] })
    return Promise.resolve({})
  })

  apiPost.mockImplementation((path) => {
    if (path === '/api/chat/sessions') return Promise.resolve({ id: 'session-qa-1', title: null })
    if (path === '/api/qa') return Promise.resolve(qaResponse)
    return Promise.resolve({})
  })

  getProfile.mockResolvedValue(profileResponse)
  getDifficultyPlan.mockResolvedValue(difficultyPlanResponse)

  apiSsePost.mockImplementation(async (path, body, handlers) => {
    if (path !== '/api/qa/stream') return
    handlers?.onStatus?.({ stage: 'retrieving', message: '正在检索相关片段...' })
    handlers?.onSources?.({ sources: qaResponse.sources, retrieved_count: 1 })
    handlers?.onStatus?.({ stage: 'generating', message: '正在生成回答...', retrieved_count: 1 })
    handlers?.onChunk?.({ delta: 'A matrix ' })
    handlers?.onChunk?.({ delta: 'is a rectangular array of numbers.' })
    handlers?.onStatus?.({ stage: 'saving', message: '正在保存会话记录...' })
    handlers?.onStatus?.({ stage: 'done', message: '回答生成完成', result: 'ok' })
    handlers?.onDone?.({ result: 'ok', mode: 'normal', retrieved_count: 1, ability_level: 'intermediate', timings: { total_ms: 123 } })
  })
})

describe('Q&A', () => {
  it('sends kb_id and question on Ask via stream endpoint', async () => {
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

    expect(apiSsePost).toHaveBeenCalledWith(
      '/api/qa/stream',
      expect.objectContaining({
        kb_id: 'kb-1',
        question: 'What is a matrix?'
      }),
      expect.any(Object)
    )
  })

  it('hides adaptive card when adaptive is disabled', async () => {
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

    let html = wrapper.html()
    expect(html).toContain('自适应依据')
    expect(html).toContain('自适应开')

    const adaptiveToggle = wrapper.findAll('button').find((btn) => btn.text().includes('自适应开'))
    expect(adaptiveToggle).toBeTruthy()
    await adaptiveToggle.trigger('click')
    await flushPromises()
    await nextTick()

    html = wrapper.html()
    expect(html).toContain('自适应关')
    expect(html).not.toContain('自适应依据')

    const textarea = wrapper.find('textarea')
    await textarea.setValue('What is a matrix?')
    await nextTick()
    await textarea.trigger('keydown.enter')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const payload = apiSsePost.mock.calls.at(-1)?.[1] || {}
    expect(payload.user_id).toBe('test')
    expect(payload.kb_id).toBe('kb-1')
  })

  it('renders streamed answer and sources in qa-log', async () => {
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
    await wrapper.find('textarea').trigger('keydown.enter')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    expect(apiSsePost).toHaveBeenCalled()
    expect(html).toContain(qaResponse.answer)
    expect(html).toContain('参考来源（1）')
    expect(html).toContain('doc')
    expect(html).toContain('来源可能来自该知识库下多个文档片段')
    expect(html).toContain('回答生成完成')
    expect(html).toContain('自适应依据')
    expect(html).toContain('薄弱知识点 Top 3')
    expect(html).toContain('矩阵乘法')
    expect(html).toContain('30%')
    expect(html).toContain('50%')
    expect(html).toContain('20%')
  })

  it('refreshes adaptive transparency after stream done', async () => {
    const { wrapper, router } = await mountAppWithRouter()

    await router.push('/qa')
    await flushPromises()
    await nextTick()
    await nextTick()

    const beforePlanCalls = getDifficultyPlan.mock.calls.length

    const kbSelect = wrapper.find('select')
    await kbSelect.setValue('kb-1')
    await flushPromises()
    await nextTick()

    await wrapper.find('textarea').setValue('What is a matrix?')
    await nextTick()
    await wrapper.find('textarea').trigger('keydown.enter')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const afterPlanCalls = getDifficultyPlan.mock.calls.length
    expect(afterPlanCalls).toBeGreaterThan(beforePlanCalls)
  })

  it('falls back to POST /api/qa when stream fails', async () => {
    apiSsePost.mockImplementationOnce(async () => {
      throw new Error('network interrupted')
    })

    const { wrapper, router } = await mountAppWithRouter()

    await router.push('/qa')
    await flushPromises()
    await nextTick()
    await nextTick()

    const kbSelect = wrapper.find('select')
    await kbSelect.setValue('kb-1')
    await flushPromises()
    await nextTick()

    await wrapper.find('textarea').setValue('What is a matrix?')
    await nextTick()
    await wrapper.find('textarea').trigger('keydown.enter')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    expect(apiPost).toHaveBeenCalledWith(
      '/api/qa',
      expect.objectContaining({
        kb_id: 'kb-1',
        question: 'What is a matrix?'
      })
    )
    expect(wrapper.html()).toContain('已回退非流式')
  })

  it('shows KB multi-document hint in learning-path context banner when focus is provided', async () => {
    const { wrapper, router } = await mountAppWithRouter()

    await router.push({
      path: '/qa',
      query: {
        kb_id: 'kb-1',
        focus: '矩阵定义',
      },
    })
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    expect(html).toContain('学习路径上下文')
    expect(html).toContain('当前学习目标')
    expect(html).toContain('矩阵定义')
    expect(html).toContain('该学习目标可能关联同一知识库中的多个文档来源')
  })

  it('auto-sends explain mode from route query and clears transient qa query params', async () => {
    apiSsePost.mockImplementationOnce(async (path, body, handlers) => {
      handlers?.onStatus?.({ stage: 'retrieving', message: '正在检索相关片段...' })
      handlers?.onSources?.({ sources: qaResponse.sources, retrieved_count: 1 })
      handlers?.onStatus?.({ stage: 'generating', message: '正在生成回答...', retrieved_count: 1 })
      handlers?.onChunk?.({ delta: explainAnswer })
      handlers?.onStatus?.({ stage: 'done', message: '回答生成完成', result: 'ok' })
      handlers?.onDone?.({
        result: 'ok',
        mode: 'explain',
        retrieved_count: 1,
        ability_level: 'intermediate',
        timings: { total_ms: 88 }
      })
    })

    const { wrapper, router } = await mountAppWithRouter()

    await router.push({
      path: '/qa',
      query: {
        kb_id: 'kb-1',
        focus: '矩阵定义',
        qa_mode: 'explain',
        qa_autosend: '1',
        qa_question: '请讲解这道错题',
        qa_from: 'quiz_wrong'
      }
    })
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    expect(apiSsePost).toHaveBeenCalledWith(
      '/api/qa/stream',
      expect.objectContaining({
        kb_id: 'kb-1',
        focus: '矩阵定义',
        mode: 'explain',
        question: '请讲解这道错题'
      }),
      expect.any(Object)
    )
    expect(wrapper.html()).toContain('分步讲解')
    expect(router.currentRoute.value.query.qa_mode).toBeUndefined()
    expect(router.currentRoute.value.query.qa_question).toBeUndefined()
    expect(router.currentRoute.value.query.focus).toBeUndefined()
  })

  it('keeps focus query for normal QA entry without autosend', async () => {
    const { router } = await mountAppWithRouter()

    await router.push({
      path: '/qa',
      query: {
        kb_id: 'kb-1',
        focus: '矩阵定义',
      },
    })
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    expect(apiSsePost).not.toHaveBeenCalled()
    expect(router.currentRoute.value.query.focus).toBe('矩阵定义')
  })
})
