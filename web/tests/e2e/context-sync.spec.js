import { test, expect } from '@playwright/test'

const apiBase = process.env.E2E_API_BASE || 'http://localhost:8000'

async function ensureBackendHealthy(request) {
  try {
    const res = await request.get(`${apiBase}/api/health`)
    return res.ok()
  } catch {
    return false
  }
}

async function ensureAuthUser(request, username = 'e2e_context_sync_user') {
  const password = 'e2e-password-123'
  const registerResp = await request.post(`${apiBase}/api/auth/register`, {
    data: { username, password, name: username },
  })
  if (registerResp.ok()) {
    return registerResp.json()
  }
  const loginResp = await request.post(`${apiBase}/api/auth/login`, {
    data: { username, password },
  })
  if (!loginResp.ok()) {
    throw new Error('Failed to create/login E2E user')
  }
  return loginResp.json()
}

async function ensureKbSelected(page) {
  const uploadCard = page.getByRole('heading', { name: '上传文档' }).locator('../..')
  const kbSelect = uploadCard.locator('select').first()
  await expect(kbSelect).toBeVisible({ timeout: 30000 })

  let options = await kbSelect
    .locator('option')
    .evaluateAll((rows) => rows.map((row) => ({ value: row.getAttribute('value') || '', label: (row.textContent || '').trim() })))

  let selectable = options.filter((item) => item.value)

  if (!selectable.length) {
    const kbName = `ctx-sync-${Date.now()}`
    await uploadCard.getByPlaceholder('新知识库名称').fill(kbName)
    await uploadCard.getByRole('button', { name: '创建' }).click()

    await expect
      .poll(async () => {
        const current = await kbSelect
          .locator('option')
          .evaluateAll((rows) => rows.map((row) => ({ value: row.getAttribute('value') || '', label: (row.textContent || '').trim() })))
        return current.filter((item) => item.value).length
      })
      .toBeGreaterThan(0)

    options = await kbSelect
      .locator('option')
      .evaluateAll((rows) => rows.map((row) => ({ value: row.getAttribute('value') || '', label: (row.textContent || '').trim() })))
    selectable = options.filter((item) => item.value)
  }

  const target = selectable[0]
  await kbSelect.selectOption(target.value)
  await expect(kbSelect).toHaveValue(target.value)
  return target.value
}

test.describe('App context sync', () => {
  test.beforeEach(async ({ request }) => {
    const healthy = await ensureBackendHealthy(request)
    test.skip(!healthy, 'Backend is not reachable at E2E_API_BASE')
  })

  test('selected kb persists across pages and refresh', async ({ page, request }) => {
    const auth = await ensureAuthUser(request, 'e2e_context_sync_user')
    await page.addInitScript((user) => {
      localStorage.setItem('gradtutor_user_id', user.user_id)
      localStorage.setItem('gradtutor_username', user.username)
      localStorage.setItem('gradtutor_name', user.name || '')
      localStorage.setItem('gradtutor_user', user.user_id)
      localStorage.setItem('gradtutor_access_token', user.access_token || '')
    }, auth)

    await page.goto('/upload')
    await expect(page.getByRole('heading', { name: '上传文档' })).toBeVisible()

    const selectedKbValue = await ensureKbSelected(page)

    await page.getByRole('link', { name: '问答' }).click()
    const qaCard = page.getByRole('heading', { name: '上下文' }).locator('../..')
    await expect(qaCard.locator('select').first()).toHaveValue(selectedKbValue)

    await page.getByRole('link', { name: '测验' }).click()
    const quizCard = page.getByRole('heading', { name: '测验生成' }).locator('../..')
    await expect(quizCard.locator('select').first()).toHaveValue(selectedKbValue)

    await page.getByRole('link', { name: '进度' }).click()
    const progressSection = page.getByRole('heading', { name: '知识库统计' }).locator('../..')
    await expect(progressSection.locator('select')).toHaveValue(selectedKbValue)

    await page.reload()
    await expect(page.getByRole('heading', { name: '知识库统计' })).toBeVisible()
    await expect(progressSection.locator('select')).toHaveValue(selectedKbValue)
  })
})
