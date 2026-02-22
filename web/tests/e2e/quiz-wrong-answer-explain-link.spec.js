import { test, expect } from '@playwright/test'

const apiBase = process.env.E2E_API_BASE || 'http://localhost:8000'

function jsonResponse(body, status = 200) {
  return {
    status,
    headers: {
      'content-type': 'application/json',
      'access-control-allow-origin': '*',
    },
    body: JSON.stringify(body),
  }
}

function sseResponse(body) {
  return {
    status: 200,
    headers: {
      'content-type': 'text/event-stream',
      'cache-control': 'no-cache',
      connection: 'keep-alive',
      'access-control-allow-origin': '*',
    },
    body,
  }
}

function buildSseEvent(event, payload) {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`
}

function nowIso() {
  return new Date().toISOString()
}

test('wrong answer can jump to QA explain mode and auto-send', async ({ page }) => {
  const state = {
    sessions: [],
    messagesBySession: {},
    qaStreamBodies: [],
    nextSessionId: 'session-e2e-qa-1',
  }

  await page.addInitScript(() => {
    localStorage.setItem('gradtutor_user_id', 'e2e-user')
    localStorage.setItem('gradtutor_username', 'e2e-user')
    localStorage.setItem('gradtutor_name', 'e2e-user')
    localStorage.setItem('gradtutor_user', 'e2e-user')
    localStorage.setItem('gradtutor_access_token', 'e2e-token')
  })

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const pathname = url.pathname
    const method = request.method()

    if (url.origin !== apiBase) {
      // Let non-target API calls pass through if API base is customized.
      return route.continue()
    }

    if (pathname === '/api/kb' && method === 'GET') {
      return route.fulfill(
        jsonResponse([
          {
            id: 'kb-1',
            user_id: 'e2e-user',
            name: '默认知识库',
            description: null,
            created_at: nowIso(),
          },
        ])
      )
    }

    if (pathname === '/api/docs' && method === 'GET') {
      return route.fulfill(jsonResponse([]))
    }

    if (pathname === '/api/profile' && method === 'GET') {
      return route.fulfill(
        jsonResponse({
          user_id: 'e2e-user',
          ability_level: 'intermediate',
          theta: 0,
          frustration_score: 0,
          weak_concepts: [],
          recent_accuracy: 0.5,
          total_attempts: 0,
          mastery_avg: 0,
          mastery_completion_rate: 0,
          updated_at: nowIso(),
        })
      )
    }

    if (pathname === '/api/chat/sessions' && method === 'GET') {
      return route.fulfill(jsonResponse(state.sessions))
    }

    if (pathname === '/api/chat/sessions' && method === 'POST') {
      const payload = request.postDataJSON()
      const session = {
        id: state.nextSessionId,
        user_id: 'e2e-user',
        kb_id: payload?.kb_id || 'kb-1',
        doc_id: payload?.doc_id || null,
        title: payload?.name || null,
        created_at: nowIso(),
      }
      state.sessions = [session, ...state.sessions]
      state.messagesBySession[session.id] = []
      return route.fulfill(jsonResponse(session))
    }

    const chatMessagesMatch = pathname.match(/^\/api\/chat\/sessions\/([^/]+)\/messages$/)
    if (chatMessagesMatch && method === 'GET') {
      const sessionId = decodeURIComponent(chatMessagesMatch[1])
      return route.fulfill(jsonResponse(state.messagesBySession[sessionId] || []))
    }

    if (pathname === '/api/quiz/generate' && method === 'POST') {
      return route.fulfill(
        jsonResponse({
          quiz_id: 'quiz-e2e-1',
          questions: [
            {
              question: '矩阵的行列式为 0 时，矩阵通常意味着什么？',
              options: ['一定可逆', '通常不可逆', '一定对称', '一定正定'],
              answer_index: 1,
              explanation: '行列式为 0 表示矩阵不可逆。',
              concepts: ['矩阵可逆性'],
            },
          ],
        })
      )
    }

    if (pathname === '/api/quiz/submit' && method === 'POST') {
      return route.fulfill(
        jsonResponse({
          score: 0,
          correct: 0,
          total: 1,
          results: [false],
          explanations: ['行列式为 0 表示矩阵不可逆，因此正确选项是 B。'],
          feedback: {
            type: 'encourage',
            message: '这类题目建议重点区分“可逆”和“行列式非零”的关系。',
          },
          next_quiz_recommendation: {
            difficulty: 'easy',
            focus_concepts: ['矩阵可逆性'],
          },
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
      )
    }

    if (pathname === '/api/qa/stream' && method === 'POST') {
      const payload = request.postDataJSON()
      state.qaStreamBodies.push(payload)

      const sessionId = payload?.session_id || state.nextSessionId
      const explainMarkdown = [
        '## 题意理解',
        '这道题在考察行列式与矩阵可逆性的关系。',
        '## 相关知识点',
        '- 行列式',
        '- 可逆矩阵',
        '## 分步解答',
        '当行列式为 0 时，矩阵不可逆，所以应选 B。[1]',
        '## 易错点',
        '容易把“行列式为 0”误判为“可逆”。',
        '## 自测问题',
        '如果矩阵可逆，它的行列式可以为 0 吗？',
      ].join('\n')

      const sources = [
        {
          source: '线性代数讲义 p.3 c.1',
          snippet: '行列式为零则矩阵不可逆',
          doc_id: 'doc-1',
          kb_id: 'kb-1',
          page: 3,
          chunk: 1,
        },
      ]

      if (!state.messagesBySession[sessionId]) {
        state.messagesBySession[sessionId] = []
      }
      state.messagesBySession[sessionId].push(
        {
          id: `msg-u-${state.messagesBySession[sessionId].length + 1}`,
          session_id: sessionId,
          role: 'user',
          content: payload.question,
          created_at: nowIso(),
        },
        {
          id: `msg-a-${state.messagesBySession[sessionId].length + 2}`,
          session_id: sessionId,
          role: 'assistant',
          content: explainMarkdown,
          created_at: nowIso(),
          sources,
        }
      )

      state.sessions = state.sessions.map((session) =>
        session.id === sessionId && !session.title
          ? { ...session, title: String(payload.question || '').slice(0, 60) }
          : session
      )

      const sseBody = [
        buildSseEvent('status', { stage: 'retrieving', message: '正在检索相关片段...' }),
        buildSseEvent('sources', { sources, retrieved_count: 1 }),
        buildSseEvent('status', {
          stage: 'generating',
          message: '正在生成回答...',
          retrieved_count: 1,
          timings: { retrieve_ms: 12 },
        }),
        buildSseEvent('chunk', { delta: explainMarkdown }),
        buildSseEvent('status', {
          stage: 'saving',
          message: '正在保存会话记录...',
          retrieved_count: 1,
          timings: { retrieve_ms: 12, generate_ms: 25 },
        }),
        buildSseEvent('status', {
          stage: 'done',
          message: '回答生成完成',
          result: 'ok',
          retrieved_count: 1,
          timings: { retrieve_ms: 12, generate_ms: 25, total_ms: 45 },
        }),
        buildSseEvent('done', {
          session_id: sessionId,
          ability_level: 'intermediate',
          mode: 'explain',
          result: 'ok',
          retrieved_count: 1,
          timings: { retrieve_ms: 12, generate_ms: 25, total_ms: 45 },
        }),
      ].join('')

      return route.fulfill(sseResponse(sseBody))
    }

    if (pathname === '/api/qa' && method === 'POST') {
      return route.fulfill(
        jsonResponse({
          answer: 'fallback answer',
          sources: [],
          session_id: state.nextSessionId,
          ability_level: 'intermediate',
          mode: 'explain',
        })
      )
    }

    return route.fulfill(jsonResponse({}))
  })

  await page.goto('/quiz')
  await expect(page.getByRole('heading', { name: '测验生成' })).toBeVisible()

  const quizCard = page.getByRole('heading', { name: '测验生成' }).locator('../..')
  const kbSelect = quizCard.locator('select').first()
  await expect(kbSelect).toHaveValue('kb-1')

  await quizCard.getByRole('button', { name: '生成新测验' }).click()
  await expect(page.getByRole('button', { name: '提交全部答案' })).toBeVisible()

  const wrongOption = page.locator('input[type="radio"][name="q-0"][value="0"]')
  await wrongOption.locator('..').click()
  await page.getByRole('button', { name: '提交全部答案' }).click()

  const explainButton = page.getByRole('button', { name: '讲解此题' })
  await expect(explainButton).toBeVisible()
  await explainButton.click()

  await expect(page.getByRole('heading', { name: 'AI 辅导对话' })).toBeVisible()
  await expect(page.getByText('讲解模式').first()).toBeVisible()
  await expect(page.getByText('题意理解').first()).toBeVisible()

  await expect
    .poll(() => state.qaStreamBodies.length, { message: 'QA explain stream should be triggered automatically' })
    .toBeGreaterThan(0)

  const qaPayload = state.qaStreamBodies.at(-1)
  expect(qaPayload.mode).toBe('explain')
  expect(qaPayload.kb_id).toBe('kb-1')
  expect(String(qaPayload.question || '')).toContain('请用讲解模式解析这道选择题')
  expect(String(qaPayload.question || '')).toContain('正确答案')
  expect(String(qaPayload.question || '')).toContain('额外要求')

  await expect
    .poll(() => new URL(page.url()).searchParams.get('qa_mode'))
    .toBe(null)
  await expect
    .poll(() => new URL(page.url()).searchParams.get('qa_question'))
    .toBe(null)
})
