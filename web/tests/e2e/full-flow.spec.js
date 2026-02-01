import path from 'path'
import { fileURLToPath } from 'url'
import { test, expect } from '@playwright/test'

const apiBase = process.env.E2E_API_BASE || 'http://localhost:8000'
const runLLM = process.env.E2E_LLM === '1'
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const fixturePath = path.resolve(__dirname, '../fixtures/sample.txt')
const fixtureName = 'sample.txt'

async function ensureBackendHealthy(request) {
  try {
    const res = await request.get(`${apiBase}/api/health`)
    return res.ok()
  } catch (err) {
    return false
  }
}

async function selectDocInCard(card, filename) {
  const select = card.locator('select').first()
  await expect(select.locator('option', { hasText: filename })).toHaveCount(1, {
    timeout: 60000
  })
  await select.selectOption({ label: filename })
}

async function waitForDocReady(page, filename) {
  const docsCard = page.getByRole('heading', { name: 'Documents' }).locator('..')
  const refreshButton = page.getByRole('button', { name: 'Refresh List' })
  const item = docsCard.locator('.list-item', { hasText: filename })

  await expect(item).toBeVisible({ timeout: 60000 })

  for (let i = 0; i < 30; i += 1) {
    const readyBadge = item.getByText('ready')
    if (await readyBadge.count()) {
      return
    }
    await refreshButton.click()
    await page.waitForTimeout(2000)
  }

  await expect(item.getByText('ready')).toBeVisible({ timeout: 60000 })
}

test.describe('GradTutor E2E', () => {
  test.beforeEach(async ({ request }) => {
    const healthy = await ensureBackendHealthy(request)
    test.skip(!healthy, 'Backend is not reachable at E2E_API_BASE')
  })

  test('basic UI loads', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'GradTutor' })).toBeVisible()
    const tabs = page.locator('.tabs')
    await expect(tabs.getByRole('button', { name: 'Upload' })).toBeVisible()
    await expect(tabs.getByRole('button', { name: 'Summary' })).toBeVisible()
    await expect(tabs.getByRole('button', { name: 'Q&A' })).toBeVisible()
    await expect(tabs.getByRole('button', { name: 'Quiz' })).toBeVisible()
    await expect(tabs.getByRole('button', { name: 'Progress' })).toBeVisible()
  })

  test('full flow: upload → summary → keypoints → QA → quiz → progress', async ({
    page
  }) => {
    test.skip(!runLLM, 'Set E2E_LLM=1 to run LLM-backed flows')

    const userId = `e2e_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const kbName = `E2E KB ${Date.now()}`

    await page.addInitScript((value) => {
      localStorage.setItem('gradtutor_user', value)
    }, userId)

    await page.goto('/')

    await page.getByRole('button', { name: 'Apply' }).click()

    const uploadCard = page.getByRole('heading', { name: 'Upload Document' }).locator('..')

    await uploadCard.getByPlaceholder('New knowledge base name').fill(kbName)
    await uploadCard.getByRole('button', { name: 'Create KB' }).click()

    const kbSelect = uploadCard.locator('select')
    await expect(kbSelect.locator('option', { hasText: kbName })).toHaveCount(1, {
      timeout: 30000
    })
    await kbSelect.selectOption({ label: kbName })

    await uploadCard.locator('input[type="file"]').setInputFiles(fixturePath)
    await uploadCard.getByRole('button', { name: 'Upload' }).click()

    await expect(uploadCard.locator('.status', { hasText: 'Upload complete.' })).toBeVisible({
      timeout: 60000
    })
    await waitForDocReady(page, fixtureName)

    await page.locator('.tabs').getByRole('button', { name: 'Summary' }).click()
    const summaryCard = page.getByRole('heading', { name: 'Generate Summary' }).locator('..')
    await selectDocInCard(summaryCard, fixtureName)
    await summaryCard.getByRole('button', { name: 'Summarize' }).click()
    await expect(summaryCard.locator('p.muted')).toBeVisible({ timeout: 120000 })

    const keypointsCard = page.getByRole('heading', { name: 'Keypoints' }).locator('..')
    await keypointsCard.getByRole('button', { name: 'Extract Keypoints' }).click()
    await expect(keypointsCard.locator('.list-item').first()).toBeVisible({
      timeout: 120000
    })

    await page.locator('.tabs').getByRole('button', { name: 'Q&A' }).click()
    const qaCard = page.getByRole('heading', { name: 'Ask a Question' }).locator('..')
    await selectDocInCard(qaCard, fixtureName)
    await qaCard.locator('textarea').fill('What is a matrix?')
    await qaCard.getByRole('button', { name: 'Ask' }).click()
    const conversationCard = page.getByRole('heading', { name: 'Conversation' }).locator('..')
    await expect(conversationCard.locator('.qa-bubble.answer')).toBeVisible({ timeout: 120000 })

    await page.locator('.tabs').getByRole('button', { name: 'Quiz' }).click()
    const quizCard = page.getByRole('heading', { name: 'Generate Quiz' }).locator('..')
    await selectDocInCard(quizCard, fixtureName)
    await quizCard.locator('input[type="number"]').fill('3')
    await quizCard.getByRole('button', { name: 'Generate Quiz' }).click()

    const quizPanel = page.getByRole('heading', { name: 'Quiz' }).locator('..')
    await expect(quizPanel.getByText('Q1.')).toBeVisible({ timeout: 120000 })

    const questionItems = quizPanel.locator('.list-item')
    const questionCount = await questionItems.count()
    for (let idx = 0; idx < questionCount; idx += 1) {
      const item = questionItems.nth(idx)
      await item.locator('input[type="radio"]').first().check()
    }
    await quizPanel.getByRole('button', { name: 'Submit Answers' }).click()
    await expect(quizPanel.getByText('Score:')).toBeVisible({ timeout: 120000 })

    await page.locator('.tabs').getByRole('button', { name: 'Progress' }).click()
    const progressCard = page.getByRole('heading', { name: 'Progress Overview' }).locator('..')
    await progressCard.getByRole('button', { name: 'Refresh' }).click()
    await expect(progressCard.getByText(/Documents:\s*\d+/)).toBeVisible({ timeout: 60000 })
    await expect(progressCard.getByText(/Questions asked:\s*\d+/)).toBeVisible()
  })
})
