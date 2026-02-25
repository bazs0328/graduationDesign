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
