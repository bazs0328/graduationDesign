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
 * 前端卡片 DOM 结构（便于维护定位器）：
 * - Upload: section > div(标题行) > h2「上传文档」; select 在同 section 内 → uploadCard = h2.locator('../..')
 * - 我的文档: section > div.flex.justify-between > div.flex.gap-3 > h2「我的文档」; 文档列表在同 section → docsCard = h2.locator('..').locator('..').locator('..')
 * - 摘要侧栏: div.bg-card > div(标题) > h2「选择文档」; select 在同 card 内 → summaryCard = h2.locator('../..')
 * - 内容摘要: section > div(标题行) > div > h2「内容摘要」; 摘要 p 在同 section 内 → summarySection = h2.locator('..').locator('..').locator('..')
 * - 核心知识点: section > div(标题行) > div > h2「核心知识点」; 要点 div.p-4 在同 section → keypointsSection = h2.locator('..').locator('..').locator('..')
 * - 问答上下文: div.bg-card > div(标题) > h2「上下文」; select 在同 card → qaContextCard = h2.locator('../..')
 * - 测验生成: section.bg-card > div(标题) > h2「测验生成」; select/button 在同 section → quizCard = h2.locator('../..')
 * - 进度知识库统计: section > div.flex-col > div(标题) + select 兄弟 → progressKbSection = h2.locator('../..')
 */

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
  await select.selectOption({ label: filename }, { timeout: 60000 })
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

test.describe('GradTutor E2E', () => {
  test.beforeEach(async ({ request }) => {
    const healthy = await ensureBackendHealthy(request)
    test.skip(!healthy, 'Backend is not reachable at E2E_API_BASE')
  })

  test('basic UI loads', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'GradTutor' })).toBeVisible()
    const nav = page.getByRole('navigation')
    await expect(nav.getByRole('link', { name: '首页' })).toBeVisible()
    await expect(nav.getByRole('link', { name: '上传' })).toBeVisible()
    await expect(nav.getByRole('link', { name: '摘要' })).toBeVisible()
    await expect(nav.getByRole('link', { name: '问答' })).toBeVisible()
    await expect(nav.getByRole('link', { name: '测验' })).toBeVisible()
    await expect(nav.getByRole('link', { name: '进度' })).toBeVisible()
  })

  test('full flow: upload → summary → keypoints → QA → quiz → progress', async ({
    page
  }) => {
    test.skip(!runLLM, 'Set E2E_LLM=1 to run LLM-backed flows')

    const kbName = 'Default'

    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'GradTutor' })).toBeVisible()
    const userIdInput = page.getByRole('complementary').getByRole('textbox')
    await userIdInput.fill('default')
    await userIdInput.blur()
    await page.waitForLoadState('load')

    await Promise.all([
      page.waitForResponse(
        (resp) => resp.url().includes('/api/kb') && resp.request().method() === 'GET',
        { timeout: 20000 }
      ),
      page.getByRole('link', { name: '上传' }).click()
    ])
    await expect(page.getByRole('heading', { name: '上传文档' })).toBeVisible()
    await expect(page.getByPlaceholder('新知识库名称')).toBeVisible()

    const uploadCard = page.getByRole('heading', { name: '上传文档' }).locator('../..')
    const kbSelect = uploadCard.locator('select').first()
    await kbSelect.selectOption({ label: kbName }, { timeout: 15000 })

    await uploadCard.locator('input[type="file"]').setInputFiles(fixturePath)
    await uploadCard.getByRole('button', { name: '上传到知识库' }).click()

    await expect(page.getByText(fixtureName).first()).toBeVisible({ timeout: 60000 })
    await waitForDocReady(page, fixtureName)

    await page.getByRole('link', { name: '摘要' }).click()
    const summaryCard = page.getByRole('heading', { name: '选择文档' }).locator('../..')
    await selectDocInCard(summaryCard, fixtureName)
    await summaryCard.getByRole('button', { name: '生成摘要' }).click()
    const summarySection = page.getByRole('heading', { name: '内容摘要' }).locator('..').locator('..').locator('..')
    await expect(summarySection.locator('p.text-lg').first()).toBeVisible({ timeout: 120000 })

    await summaryCard.getByRole('button', { name: '提取要点' }).click()
    const keypointsSection = page.getByRole('heading', { name: '核心知识点' }).locator('..').locator('..').locator('..')
    await expect(keypointsSection.locator('div.p-4').first()).toBeVisible({ timeout: 120000 })

    await page.getByRole('link', { name: '问答' }).click()
    const qaContextCard = page.getByRole('heading', { name: '上下文' }).locator('../..')
    await qaContextCard.locator('select').first().selectOption({ label: kbName })
    await page.getByPlaceholder('在此输入你的问题…').fill('What is a matrix?')
    await page.getByPlaceholder('在此输入你的问题…').locator('..').getByRole('button').click()
    await expect(page.getByText('AI 辅导')).toBeVisible({ timeout: 120000 })

    await page.getByRole('link', { name: '测验' }).click()
    const quizCard = page.getByRole('heading', { name: '测验生成' }).locator('../..')
    await quizCard.locator('select').first().selectOption({ label: kbName })
    await quizCard.locator('input[type="number"]').fill('3')
    await quizCard.getByRole('button', { name: '生成新测验' }).click()

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
    await expect(page.getByRole('heading', { name: '知识库统计' })).toBeVisible()
    const progressKbSection = page.getByRole('heading', { name: '知识库统计' }).locator('../..')
    await progressKbSection.locator('select').selectOption({ label: kbName })
    await expect(page.getByText(/文档数|测验数/).first()).toBeVisible({ timeout: 60000 })
  })
})
