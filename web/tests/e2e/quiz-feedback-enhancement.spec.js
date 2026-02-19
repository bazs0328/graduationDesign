import path from 'path'
import { fileURLToPath } from 'url'
import { test, expect } from '@playwright/test'

const apiBase = process.env.E2E_API_BASE || 'http://localhost:8000'
const runLLM = process.env.E2E_LLM === '1'
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const fixturePath = path.resolve(__dirname, '../fixtures/sample.txt')
const fixtureName = 'sample.txt'

/**
 * E2E 测试：测验反馈增强功能
 * 验证完整流程：生成测验 → 提交答案 → 查看能力变化 → 错题分组 → 针对性练习
 */

async function ensureBackendHealthy(request) {
  try {
    const res = await request.get(`${apiBase}/api/health`)
    return res.ok()
  } catch (err) {
    return false
  }
}

async function waitForDocReady(page, filename) {
  const docsCard = page.getByRole('heading', { name: '我的文档' }).locator('..').locator('..').locator('..')
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

async function waitForQuizGenerated(page) {
  await expect(page.getByRole('button', { name: '提交全部答案' })).toBeVisible({
    timeout: 120000
  })
  await page.waitForTimeout(1000)
}

async function submitQuizWithWrongAnswers(page, wrongQuestionIndices) {
  const radioNames = await page.locator('input[type="radio"][name^="q-"]').evaluateAll((els) =>
    [...new Set(els.map((e) => e.getAttribute('name')))].sort()
  )
  
  for (let i = 0; i < radioNames.length; i++) {
    const name = radioNames[i]
    const questionIndex = parseInt(name.replace('q-', ''), 10)
    const shouldBeWrong = wrongQuestionIndices.includes(questionIndex)
    
    const radios = page.locator(`input[type="radio"][name="${name}"]`)
    const count = await radios.count()
    
    if (shouldBeWrong && count > 1) {
      await radios.nth(1).locator('..').click()
    } else {
      await radios.first().locator('..').click()
    }
  }
  
  const submitResponsePromise = page.waitForResponse(
    (resp) => resp.url().includes('/api/quiz/submit') && resp.status() === 200,
    { timeout: 120000 }
  )
  
  await page.getByRole('button', { name: '提交全部答案' }).click()
  await submitResponsePromise
  
  await expect(page.getByText(/正确/)).toBeVisible({ timeout: 5000 })
  await page.waitForTimeout(2000)
}

test.describe('Quiz Feedback Enhancement', () => {
  test.beforeEach(async ({ request }) => {
    const healthy = await ensureBackendHealthy(request)
    test.skip(!healthy, 'Backend is not reachable at E2E_API_BASE')
  })

  test('full flow: generate → submit → view feedback → targeted practice', async ({
    page
  }) => {
    test.skip(!runLLM, 'Set E2E_LLM=1 to run LLM-backed flows')

    const kbName = 'Default'
    const quizCount = 5
    const testUserId = 'e2e_test_user'

    // Set user ID in localStorage before navigation to avoid login redirect
    await page.goto('/')
    await page.evaluate((userId) => {
      localStorage.setItem('gradtutor_user_id', userId)
      localStorage.setItem('gradtutor_username', userId)
      localStorage.setItem('gradtutor_name', userId)
      localStorage.setItem('gradtutor_user', userId)
    }, testUserId)
    
    // Reload page to apply localStorage changes
    await page.reload()
    await expect(page.getByRole('heading', { name: 'GradTutor' })).toBeVisible()
    await page.waitForLoadState('load')

    await Promise.all([
      page.waitForResponse(
        (resp) => resp.url().includes('/api/kb') && resp.request().method() === 'GET',
        { timeout: 20000 }
      ),
      page.getByRole('link', { name: '上传' }).click()
    ])
    await expect(page.getByRole('heading', { name: '上传文档' })).toBeVisible()

    const uploadCard = page.getByRole('heading', { name: '上传文档' }).locator('../..')
    const kbSelect = uploadCard.locator('select').first()
    await kbSelect.selectOption({ label: kbName }, { timeout: 15000 })

    await uploadCard.locator('input[type="file"]').setInputFiles(fixturePath)
    await uploadCard.getByRole('button', { name: '上传到知识库' }).click()

    await expect(page.getByText(fixtureName).first()).toBeVisible({ timeout: 60000 })
    await waitForDocReady(page, fixtureName)

    await page.getByRole('link', { name: '测验' }).click()
    const quizCard = page.getByRole('heading', { name: '测验生成' }).locator('../..')
    await quizCard.locator('select').first().selectOption({ label: kbName })
    await quizCard.locator('input[type="number"]').fill(quizCount.toString())

    const generateResponsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/quiz/generate') && resp.status() === 200,
      { timeout: 120000 }
    )

    await quizCard.getByRole('button', { name: '生成新测验' }).click()
    await generateResponsePromise
    await waitForQuizGenerated(page)

    const questions = await page.locator('[id^="question-"]').all()
    expect(questions.length).toBeGreaterThan(0)
    expect(questions.length).toBeGreaterThanOrEqual(quizCount)

    const wrongIndices = [0, 1]
    await submitQuizWithWrongAnswers(page, wrongIndices)

    const lastResultCard = page.getByRole('heading', { name: '上次结果' }).locator('../..')
    await expect(lastResultCard).toBeVisible()

    const profileDeltaSection = lastResultCard.getByText('能力变化')
    if (await profileDeltaSection.count() > 0) {
      await expect(profileDeltaSection).toBeVisible()
      
      // Locate the accuracy delta container (div with "准确率" label)
      const accuracyContainer = lastResultCard.getByText('准确率').locator('..')
      await expect(accuracyContainer).toBeVisible()
      
      // Get the numeric value paragraph (second <p> in the container)
      const accuracyValue = accuracyContainer.locator('p').nth(1)
      await expect(accuracyValue).toBeVisible()
      
      const accuracyText = await accuracyValue.textContent()
      // Match format: "+/-XX.X %" with optional arrow (↑ or ↓)
      expect(accuracyText).toMatch(/[+-]\d+\.\d+\s*%/)
      
      // Verify frustration delta similarly
      const frustrationContainer = lastResultCard.getByText('挫败感').locator('..')
      await expect(frustrationContainer).toBeVisible()
      
      const frustrationValue = frustrationContainer.locator('p').nth(1)
      await expect(frustrationValue).toBeVisible()
      
      const frustrationText = await frustrationValue.textContent()
      // Match format: "+/-X.XX" with optional arrow
      expect(frustrationText).toMatch(/[+-]\d+\.\d+/)
    }

    const wrongGroupsSection = page.getByRole('heading', { name: '错题知识点归类' })
    if (await wrongGroupsSection.count() > 0) {
      await expect(wrongGroupsSection).toBeVisible()
      
      const hintText = page.getByText('点击题号可跳转到对应题目')
      await expect(hintText).toBeVisible()
      
      const targetedButton = page.getByRole('button', { name: '针对薄弱点再练' })
      await expect(targetedButton).toBeVisible()
      
      // Locate the grid container that holds all concept groups
      // Structure: heading -> div (flex container) -> div (parent) -> div (grid container) -> groups
      const groupsGrid = wrongGroupsSection.locator('..').locator('..').locator('..').locator('div.grid')
      await expect(groupsGrid).toBeVisible()
      
      // Find all concept groups within the grid container
      // Each group is a div with "border border-border" class that contains a p.text-primary
      const conceptGroups = groupsGrid.locator('div.border.border-border')
      const groupCount = await conceptGroups.count()
      expect(groupCount).toBeGreaterThan(0)
      
      for (let i = 0; i < groupCount; i++) {
        const group = conceptGroups.nth(i)
        const conceptName = await group.locator('.text-primary').textContent()
        expect(conceptName).toBeTruthy()
        
        const questionButtons = group.getByRole('button', { name: /^第 \d+ 题$/ })
        const buttonCount = await questionButtons.count()
        expect(buttonCount).toBeGreaterThan(0)
      }
      
      const firstQuestionButton = wrongGroupsSection
        .locator('../..')
        .locator('button')
        .filter({ hasText: /^第 \d+ 题$/ })
        .first()
      
      if (await firstQuestionButton.count() > 0) {
        const buttonText = await firstQuestionButton.textContent()
        const questionNumber = parseInt(buttonText.match(/\d+/)[0], 10)
        
        await firstQuestionButton.click()
        await page.waitForTimeout(500)
        
        const targetQuestion = page.locator(`#question-${questionNumber}`)
        await expect(targetQuestion).toBeVisible()
        
        const isInViewport = await targetQuestion.evaluate((el) => {
          const rect = el.getBoundingClientRect()
          return (
            rect.top >= 0 &&
            rect.left >= 0 &&
            rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
            rect.right <= (window.innerWidth || document.documentElement.clientWidth)
          )
        })
        expect(isInViewport).toBeTruthy()
      }
      
      const concepts = []
      for (let i = 0; i < groupCount; i++) {
        const group = conceptGroups.nth(i)
        const conceptName = await group.locator('.text-primary').textContent()
        concepts.push(conceptName.trim())
      }
      
      let interceptedRequest = null
      await page.route('**/api/quiz/generate', async (route) => {
        const request = route.request()
        const postData = request.postDataJSON()
        interceptedRequest = postData
        await route.continue()
      })
      
      const generateResponsePromise2 = page.waitForResponse(
        (resp) => resp.url().includes('/api/quiz/generate') && resp.status() === 200,
        { timeout: 120000 }
      )
      
      await targetedButton.click()
      await generateResponsePromise2
      
      if (interceptedRequest) {
        expect(interceptedRequest).toHaveProperty('focus_concepts')
        expect(Array.isArray(interceptedRequest.focus_concepts)).toBeTruthy()
        expect(interceptedRequest.focus_concepts.length).toBeGreaterThan(0)
        
        for (const concept of concepts) {
          expect(interceptedRequest.focus_concepts).toContain(concept)
        }
      }
      
      await waitForQuizGenerated(page)
      
      const newQuestions = await page.locator('[id^="question-"]').all()
      expect(newQuestions.length).toBeGreaterThan(0)
    }
  })
})
