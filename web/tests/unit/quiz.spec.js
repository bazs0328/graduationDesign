import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

import App from '@/App.vue'
import { routes } from '@/router'
import { apiGet, apiPost, apiSsePost, apiGetBlob } from '@/api'

vi.mock('@/api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    apiSsePost: vi.fn(),
    apiGetBlob: vi.fn(),
  }
})

const kbFixture = { id: 'kb-1', name: 'Default' }
const docsFixture = [
  { id: 'doc-1', filename: 'Doc A.pdf', kb_id: 'kb-1' },
  { id: 'doc-2', filename: 'Doc B.pdf', kb_id: 'kb-1' },
]
const groupedKeypointsFixture = [
  {
    id: 'gkp-1',
    text: '概念A',
    member_count: 2,
    source_doc_ids: ['doc-1'],
  },
  {
    id: 'gkp-2',
    text: '概念B',
    member_count: 1,
    source_doc_ids: ['doc-2'],
  },
  {
    id: 'gkp-3',
    text: '共享概念',
    member_count: 3,
    source_doc_ids: ['doc-1', 'doc-2'],
  },
]

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
    routes,
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(App, {
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  await nextTick()
  return { wrapper, router }
}

function mockQuizFocusApi({
  docs = docsFixture,
  groupedKeypoints = groupedKeypointsFixture,
} = {}) {
  apiGet.mockImplementation((path) => {
    if (path.startsWith('/api/kb')) return Promise.resolve([kbFixture])
    if (path.startsWith('/api/profile')) return Promise.resolve({ ability_level: 'intermediate' })
    if (path.startsWith('/api/chat/sessions')) return Promise.resolve([])
    if (path.startsWith('/api/docs')) return Promise.resolve(docs)
    if (path.startsWith('/api/keypoints/kb/')) {
      return Promise.resolve({
        keypoints: groupedKeypoints,
        grouped: true,
        raw_count: groupedKeypoints.length,
        group_count: groupedKeypoints.length,
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
        last_activity: null,
      })
    }
    if (path.startsWith('/api/activity')) return Promise.resolve({ items: [] })
    if (path.startsWith('/api/recommendations')) return Promise.resolve({ items: [] })
    return Promise.resolve({})
  })
}

function getQuizSelects(wrapper) {
  const selects = wrapper.findAll('select')
  return {
    kb: selects.find((sel) => sel.text().includes('Default')) || selects.at(0),
    doc: selects.find((sel) => sel.text().includes('不限定（整库测验）')),
    focus: selects.find((sel) => sel.text().includes('知识点')),
  }
}

function getOptionTexts(selectWrapper) {
  if (!selectWrapper?.exists?.()) return []
  return selectWrapper.findAll('option').map((opt) => opt.text())
}

async function openQuizAndSelectKb(wrapper, router, kbId = 'kb-1') {
  await router.push('/quiz')
  await flushPromises()
  await nextTick()
  await nextTick()

  const { kb } = getQuizSelects(wrapper)
  expect(kb?.exists()).toBe(true)
  await kb.setValue(kbId)
  await flushPromises()
  await nextTick()
  await flushPromises()
  await nextTick()
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiSsePost.mockReset()
  apiGetBlob.mockReset()
  localStorage.clear()
  apiGetBlob.mockResolvedValue(new Blob(['img'], { type: 'image/png' }))

  apiGet.mockImplementation((path) => {
    if (path.startsWith('/api/kb')) return Promise.resolve([kbFixture])
    if (path.startsWith('/api/profile')) return Promise.resolve({ ability_level: 'intermediate' })
    if (path.startsWith('/api/chat/sessions')) return Promise.resolve([])
    if (path.startsWith('/api/docs')) return Promise.resolve([])
    if (path.startsWith('/api/progress')) {
      return Promise.resolve({
        total_docs: 1,
        total_quizzes: 0,
        total_attempts: 0,
        total_questions: 0,
        total_summaries: 0,
        total_keypoints: 0,
        avg_score: 0,
        last_activity: null,
      })
    }
    if (path.startsWith('/api/activity')) return Promise.resolve({ items: [] })
    if (path.startsWith('/api/recommendations')) return Promise.resolve({ items: [] })
    return Promise.resolve({})
  })

  apiPost.mockImplementation((path) => {
    if (path === '/api/quiz/generate') {
      return Promise.resolve({
        quiz_id: 'quiz-1',
        questions: [
          {
            question: '矩阵的行列式为零意味着什么？',
            options: ['可逆', '不可逆', '对称', '正定'],
            answer_index: 1,
            explanation: '行列式为零表示矩阵不可逆。',
            concepts: ['矩阵可逆性'],
          },
        ],
      })
    }
    if (path === '/api/quiz/submit') {
      return Promise.resolve({
        score: 0,
        correct: 0,
        total: 1,
        results: [false],
        explanations: ['因为行列式为零，所以矩阵不可逆。'],
        feedback: null,
        next_quiz_recommendation: null,
        profile_delta: {
          theta_delta: -0.1,
          frustration_delta: 0.1,
          recent_accuracy_delta: -0.2,
          ability_level_changed: false,
        },
        wrong_questions_by_concept: [
          { concept: '矩阵可逆性', question_indices: [1] },
        ],
        mastery_updates: [],
      })
    }
    if (path === '/api/chat/sessions') {
      return Promise.resolve({ id: 'session-1', title: null })
    }
    if (path === '/api/qa') {
      return Promise.resolve({ answer: 'fallback', sources: [], mode: 'explain', ability_level: 'intermediate' })
    }
    return Promise.resolve({})
  })

  apiSsePost.mockResolvedValue(undefined)

  global.URL.createObjectURL = vi.fn(() => 'blob:test-image')
  global.URL.revokeObjectURL = vi.fn(() => {})
})

describe('Quiz wrong-answer explain link', () => {
  it('navigates to /qa with explain autosend query payload', async () => {
    const pendingSse = new Promise(() => {})
    apiSsePost.mockImplementation(() => pendingSse)

    const { wrapper, router } = await mountAppWithRouter()
    const pushSpy = vi.spyOn(router, 'push')

    await router.push('/quiz')
    await flushPromises()
    await nextTick()
    await nextTick()

    const quizCard = wrapper.findAll('select').at(0)
    expect(quizCard?.exists()).toBe(true)
    await quizCard.setValue('kb-1')
    await flushPromises()
    await nextTick()

    const generateButton = wrapper.findAll('button').find((btn) => btn.text().includes('生成新测验'))
    expect(generateButton).toBeTruthy()
    await generateButton.trigger('click')
    await flushPromises()
    await nextTick()

    const firstWrongRadio = wrapper.find('input[type="radio"][name="q-0"][value="0"]')
    await firstWrongRadio.setValue(true)
    await nextTick()

    const submitButton = wrapper.findAll('button').find((btn) => btn.text().includes('提交全部答案'))
    expect(submitButton).toBeTruthy()
    await submitButton.trigger('click')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const explainButton = wrapper.findAll('button').find((btn) => btn.text().includes('讲解此题'))
    expect(explainButton).toBeTruthy()
    await explainButton.trigger('click')
    await flushPromises()
    await nextTick()

    expect(pushSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/qa',
        query: expect.objectContaining({
          qa_mode: 'explain',
          qa_autosend: '1',
          qa_from: 'quiz_wrong',
        }),
      })
    )
    const pushArg = pushSpy.mock.calls.at(-1)?.[0]
    expect(String(pushArg?.query?.qa_question || '')).toContain('请用讲解模式解析这道选择题')
  })

  it('opens and closes image lightbox for quiz question image', async () => {
    apiPost.mockImplementation((path) => {
      if (path === '/api/quiz/generate') {
        return Promise.resolve({
          quiz_id: 'quiz-1',
          questions: [
            {
              question: '根据图1判断图形的对称轴。',
              options: ['x轴', 'y轴', '原点', '无'],
              answer_index: 1,
              explanation: '图1 显示关于 y 轴对称。',
              concepts: ['矩阵变换'],
              image: {
                url: '/api/docs/doc-1/image?page=1&chunk=2',
                caption: '图1 关于 y 轴对称示意图',
              },
            },
          ],
        })
      }
      if (path === '/api/quiz/submit') {
        return Promise.resolve({
          score: 1,
          correct: 1,
          total: 1,
          results: [true],
          explanations: ['解析'],
          feedback: null,
          next_quiz_recommendation: null,
          profile_delta: null,
          wrong_questions_by_concept: [],
          mastery_updates: [],
        })
      }
      return Promise.resolve({})
    })

    const { wrapper, router } = await mountAppWithRouter()

    await router.push('/quiz')
    await flushPromises()
    await nextTick()
    await nextTick()

    const kbSelect = wrapper.findAll('select').at(0)
    await kbSelect.setValue('kb-1')
    await flushPromises()
    await nextTick()

    const generateButton = wrapper.findAll('button').find((btn) => btn.text().includes('生成新测验'))
    await generateButton.trigger('click')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const previewButton = wrapper.find('button[aria-label^="打开题目配图预览"]')
    expect(previewButton.exists()).toBe(true)
    await previewButton.trigger('click')
    await flushPromises()
    await nextTick()

    expect(document.body.querySelector('[role="dialog"]')).toBeTruthy()
    expect(document.body.textContent).toContain('第 1 题配图')
    expect(document.body.textContent).toContain('图1 关于 y 轴对称示意图')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    await nextTick()

    expect(document.body.querySelector('[role="dialog"]')).toBeFalsy()
    wrapper.unmount()
  })

  it('shows KB aggregation wording in mastery updates and wrong-question groups', async () => {
    apiPost.mockImplementation((path) => {
      if (path === '/api/quiz/generate') {
        return Promise.resolve({
          quiz_id: 'quiz-1',
          questions: [
            {
              question: '矩阵的行列式为零意味着什么？',
              options: ['可逆', '不可逆', '对称', '正定'],
              answer_index: 1,
              explanation: '行列式为零表示矩阵不可逆。',
              concepts: ['矩阵可逆性'],
            },
          ],
        })
      }
      if (path === '/api/quiz/submit') {
        return Promise.resolve({
          score: 0,
          correct: 0,
          total: 1,
          results: [false],
          explanations: ['因为行列式为零，所以矩阵不可逆。'],
          feedback: null,
          next_quiz_recommendation: null,
          profile_delta: null,
          wrong_questions_by_concept: [{ concept: '矩阵可逆性', question_indices: [1] }],
          mastery_updates: [
            {
              keypoint_id: 'kp-1',
              text: '矩阵可逆性',
              old_level: 0.4,
              new_level: 0.3,
            },
          ],
        })
      }
      if (path === '/api/chat/sessions') {
        return Promise.resolve({ id: 'session-1', title: null })
      }
      return Promise.resolve({})
    })

    const { wrapper, router } = await mountAppWithRouter()

    await router.push('/quiz')
    await flushPromises()
    await nextTick()
    await nextTick()

    const kbSelect = wrapper.findAll('select').at(0)
    expect(kbSelect?.exists()).toBe(true)
    await kbSelect.setValue('kb-1')
    await flushPromises()
    await nextTick()

    const generateButton = wrapper.findAll('button').find((btn) => btn.text().includes('生成新测验'))
    expect(generateButton).toBeTruthy()
    await generateButton.trigger('click')
    await flushPromises()
    await nextTick()

    const firstWrongRadio = wrapper.find('input[type="radio"][name="q-0"][value="0"]')
    await firstWrongRadio.setValue(true)
    await nextTick()

    const submitButton = wrapper.findAll('button').find((btn) => btn.text().includes('提交全部答案'))
    expect(submitButton).toBeTruthy()
    await submitButton.trigger('click')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    expect(html).toContain('知识点掌握度变化')
    expect(html).toContain('以下知识点反馈已按知识库口径去重合并统计')
    expect(html).toContain('概念名称可能与单文档表述不同，但会映射到同一知识点')
  })
})

describe('Quiz focus concept scoping', () => {
  it('shows KB aggregated focus options and narrows them by selected document', async () => {
    mockQuizFocusApi()
    const { wrapper, router } = await mountAppWithRouter()

    await openQuizAndSelectKb(wrapper, router)

    let { doc, focus } = getQuizSelects(wrapper)
    expect(doc?.exists()).toBe(true)
    expect(focus?.exists()).toBe(true)

    let options = getOptionTexts(focus)
    expect(options).toContain('请选择知识点')
    expect(options).toContain('概念A')
    expect(options).toContain('概念B')
    expect(options).toContain('共享概念')

    await doc.setValue('doc-1')
    await nextTick()

    ;({ focus } = getQuizSelects(wrapper))
    options = getOptionTexts(focus)
    expect(options).toContain('概念A')
    expect(options).toContain('共享概念')
    expect(options).not.toContain('概念B')
  })

  it('removes selected focus concepts that fall outside the new document scope', async () => {
    mockQuizFocusApi()
    const { wrapper, router } = await mountAppWithRouter()

    await openQuizAndSelectKb(wrapper, router)

    let { doc, focus } = getQuizSelects(wrapper)
    await doc.setValue('doc-1')
    await nextTick()

    ;({ focus } = getQuizSelects(wrapper))
    await focus.setValue('概念A')
    await nextTick()

    const addButton = wrapper.findAll('button').find((btn) => btn.text().includes('添加'))
    expect(addButton).toBeTruthy()
    await addButton.trigger('click')
    await flushPromises()
    await nextTick()

    expect(wrapper.text()).toContain('概念A')

    ;({ doc } = getQuizSelects(wrapper))
    await doc.setValue('doc-2')
    await flushPromises()
    await nextTick()

    const chips = wrapper.findAll('span').filter((node) => node.text() === '概念A')
    expect(chips.length).toBe(0)
  })

  it('uses doc-specific empty label when selected document has no aggregated focus options', async () => {
    mockQuizFocusApi({ groupedKeypoints: [] })
    const { wrapper, router } = await mountAppWithRouter()

    await openQuizAndSelectKb(wrapper, router)

    let { doc, focus } = getQuizSelects(wrapper)
    expect(getOptionTexts(focus)).toContain('暂无可选聚合知识点')

    await doc.setValue('doc-1')
    await nextTick()

    ;({ focus } = getQuizSelects(wrapper))
    expect(getOptionTexts(focus)).toContain('该文档暂无可选聚合知识点')
  })

  it('does not raw-fallback route focus when a document is selected and focus is out of scope', async () => {
    mockQuizFocusApi()
    const generatePayloads = []
    const fallbackApiPost = apiPost.getMockImplementation()
    apiPost.mockImplementation((path, payload) => {
      if (path === '/api/quiz/generate') {
        generatePayloads.push(payload)
      }
      return fallbackApiPost(path, payload)
    })

    const { router } = await mountAppWithRouter()

    await router.push('/quiz?kb_id=kb-1&doc_id=doc-1&focus=路由外部概念')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const payload = generatePayloads.at(-1)
    expect(payload).toBeTruthy()
    expect(payload.kb_id).toBe('kb-1')
    expect(payload.doc_id).toBe('doc-1')
    expect(payload.focus_concepts).toBeUndefined()
  })

  it('keeps raw fallback route focus when no document is selected', async () => {
    mockQuizFocusApi()
    const generatePayloads = []
    const fallbackApiPost = apiPost.getMockImplementation()
    apiPost.mockImplementation((path, payload) => {
      if (path === '/api/quiz/generate') {
        generatePayloads.push(payload)
      }
      return fallbackApiPost(path, payload)
    })

    const { router } = await mountAppWithRouter()

    await router.push('/quiz?kb_id=kb-1&focus=路由外部概念')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const payload = generatePayloads.at(-1)
    expect(payload).toBeTruthy()
    expect(payload.kb_id).toBe('kb-1')
    expect(payload.doc_id).toBeUndefined()
    expect(payload.focus_concepts).toEqual(['路由外部概念'])
  })
})
