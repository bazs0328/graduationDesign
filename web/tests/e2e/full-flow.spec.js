import path from 'path'
import { fileURLToPath } from 'url'
import { test, expect } from '@playwright/test'

const apiBase = process.env.E2E_API_BASE || 'http://localhost:8000'
const runLLM = process.env.E2E_LLM === '1'
const forcedUsername = process.env.E2E_USERNAME || ''
const forcedPassword = process.env.E2E_PASSWORD || 'e2e-password-123'
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const fixturePath = path.resolve(__dirname, '../fixtures/sample.txt')
const fixtureName = 'sample.txt'

/**
 * 前端关键卡片统一通过 data-testid 定位，避免用户可见标题调整时联动打断 E2E。
 */

async function ensureBackendHealthy(request) {
  try {
    const res = await request.get(`${apiBase}/api/health`)
    return res.ok()
  } catch (err) {
    return false
  }
}

async function ensureAuthUser(request, username = 'e2e_full_flow_user') {
  const resolvedUsername = forcedUsername || username
  const password = forcedPassword
  const registerResp = await request.post(`${apiBase}/api/auth/register`, {
    data: { username: resolvedUsername, password, name: resolvedUsername }
  })
  if (registerResp.ok()) {
    return registerResp.json()
  }
  const loginResp = await request.post(`${apiBase}/api/auth/login`, {
    data: { username: resolvedUsername, password }
  })
  if (!loginResp.ok()) {
    throw new Error('Failed to create/login E2E user')
  }
  return loginResp.json()
}

async function selectDocInCard(card, filename) {
  const select = card.locator('select').first()
  await select.selectOption({ label: filename }, { timeout: 60000 })
}

async function ensureKbSelected(uploadCard) {
  const kbSelect = uploadCard.locator('select').first()
  const options = await kbSelect
    .locator('option')
    .evaluateAll((rows) => rows.map((row) => ({
      value: row.getAttribute('value') || '',
      label: (row.textContent || '').trim(),
    })))

  const target = options.find((item) => item.value)
  if (!target) {
    throw new Error('No selectable knowledge base option found')
  }

  await kbSelect.selectOption(target.value, { timeout: 15000 })
  await expect(kbSelect).toHaveValue(target.value)
  return target
}

async function waitForDocReady(page, filename) {
  const docsCard = page.getByTestId('upload-documents-card')
  const refreshButton = page.getByRole('button', { name: '刷新列表' })
  const item = docsCard.locator('div').filter({ hasText: filename }).first()

  await expect(item).toBeVisible({ timeout: 60000 })

  for (let i = 0; i < 30; i += 1) {
    const readyBadge = item.getByText('就绪')
    if (await readyBadge.count()) {
      return
    }
    await refreshButton.click()
    await page.waitForTimeout(2000)
  }

  await expect(item.getByText('就绪')).toBeVisible({ timeout: 60000 })
}

test.describe('StudyCompass E2E', () => {
  test.beforeEach(async ({ request }) => {
    const healthy = await ensureBackendHealthy(request)
    test.skip(!healthy, 'Backend is not reachable at E2E_API_BASE')
  })

  test('basic UI loads', async ({ page, request }) => {
    const auth = await ensureAuthUser(request, 'e2e_basic_ui_user')
    await page.addInitScript((user) => {
      localStorage.setItem('gradtutor_user_id', user.user_id)
      localStorage.setItem('gradtutor_username', user.username)
      localStorage.setItem('gradtutor_name', user.name || '')
      localStorage.setItem('gradtutor_user', user.user_id)
      localStorage.setItem('gradtutor_access_token', user.access_token || '')
    }, auth)
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'StudyCompass' })).toBeVisible()
    const nav = page.getByRole('navigation')
    await expect(nav.getByRole('link', { name: '首页' })).toBeVisible()
    await expect(nav.getByRole('link', { name: '上传' })).toBeVisible()
    await expect(nav.getByRole('link', { name: '摘要' })).toBeVisible()
    await expect(nav.getByRole('link', { name: '问答' })).toBeVisible()
    await expect(nav.getByRole('link', { name: '测验' })).toBeVisible()
    await expect(nav.getByRole('link', { name: '进度' })).toBeVisible()
  })

  test('full flow: upload → summary → keypoints → QA → quiz → progress', async ({
    page,
    request
  }) => {
    test.skip(!runLLM, 'Set E2E_LLM=1 to run LLM-backed flows')

    const auth = await ensureAuthUser(request, 'e2e_full_flow_llm_user')
    await page.addInitScript((user) => {
      localStorage.setItem('gradtutor_user_id', user.user_id)
      localStorage.setItem('gradtutor_username', user.username)
      localStorage.setItem('gradtutor_name', user.name || '')
      localStorage.setItem('gradtutor_user', user.user_id)
      localStorage.setItem('gradtutor_access_token', user.access_token || '')
    }, auth)

    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'StudyCompass' })).toBeVisible()
    await page.waitForLoadState('load')

    await Promise.all([
      page.waitForResponse(
        (resp) => resp.url().includes('/api/kb') && resp.request().method() === 'GET',
        { timeout: 20000 }
      ),
      page.getByRole('link', { name: '上传' }).click()
    ])
    const uploadCard = page.getByTestId('upload-current-kb-card')
    await expect(uploadCard).toBeVisible()

    const selectedKb = await ensureKbSelected(uploadCard)

    await uploadCard.locator('input[type="file"]').setInputFiles(fixturePath)
    await uploadCard.getByRole('button', { name: '上传文档' }).click()

    await expect(page.getByText(fixtureName).first()).toBeVisible({ timeout: 60000 })
    await waitForDocReady(page, fixtureName)

    await page.getByRole('link', { name: '摘要' }).click()
    const summaryCard = page.getByTestId('summary-current-doc-card')
    await selectDocInCard(summaryCard, fixtureName)
    await summaryCard.getByRole('button', { name: '生成摘要' }).click()
    const summarySection = page.getByTestId('summary-result-card')
    await expect(summarySection.locator('.summary-markdown').first()).toBeVisible({ timeout: 120000 })

    await summaryCard.getByRole('button', { name: '提取要点' }).click()
    const keypointsSection = page.getByTestId('summary-keypoints-card')
    await expect(keypointsSection.locator('div.p-4').first()).toBeVisible({ timeout: 120000 })

    await page.getByRole('link', { name: '问答' }).click()
    const qaContextCard = page.getByTestId('qa-scope-card')
    await qaContextCard.locator('select').first().selectOption(selectedKb.value)
    await page.getByPlaceholder('在此输入你的问题…').fill('What is a matrix?')
    await page.getByPlaceholder('在此输入你的问题…').locator('..').getByRole('button').click()
    await expect(page.getByText('学习助手')).toBeVisible({ timeout: 120000 })

    await page.getByRole('link', { name: '测验' }).click()
    const quizCard = page.getByTestId('quiz-setup-card')
    await quizCard.locator('select').first().selectOption(selectedKb.value)
    await quizCard.locator('input[type="number"]').fill('3')
    await quizCard.getByRole('button', { name: '生成测验' }).click()

    await expect(page.getByRole('button', { name: '提交全部答案' })).toBeVisible({
      timeout: 120000
    })
    const radioNames = await page.locator('input[type="radio"][name^="q-"]').evaluateAll((els) =>
      [...new Set(els.map((e) => e.getAttribute('name')))].sort()
    )
    for (const name of radioNames) {
      await page.locator(`input[type="radio"][name="${name}"]`).first().locator('..').click()
    }
    await page.getByRole('button', { name: '提交全部答案' }).click()
    await expect(page.getByText(/正确/)).toBeVisible({ timeout: 120000 })

    await page.getByRole('link', { name: '进度' }).click()
    const progressKbSection = page.getByTestId('progress-kb-stats-card')
    await expect(progressKbSection).toBeVisible()
    await progressKbSection.locator('select').selectOption(selectedKb.value)
    await expect(page.getByText(/文档数|测验数/).first()).toBeVisible({ timeout: 60000 })
  })
})
