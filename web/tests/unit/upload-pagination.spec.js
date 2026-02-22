import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

import App from '@/App.vue'
import { routes } from '@/router'
import { apiDelete, apiGet, apiPatch, apiPost, apiUploadWithProgress } from '@/api'

vi.mock('@/api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    apiPatch: vi.fn(),
    apiDelete: vi.fn(),
    apiUploadWithProgress: vi.fn(),
  }
})

const kbFixture = { id: 'kb-1', name: '默认知识库' }

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

function parsePath(path) {
  return new URL(path, 'http://localhost')
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
  apiPatch.mockReset()
  apiDelete.mockReset()
  apiUploadWithProgress.mockReset()
  localStorage.clear()

  apiGet.mockImplementation((path) => {
    const url = parsePath(path)
    if (url.pathname === '/api/kb') {
      return Promise.resolve([kbFixture])
    }
    if (url.pathname === '/api/docs/tasks') {
      return Promise.resolve({
        processing: [],
        error: [],
        processing_count: 0,
        error_count: 0,
        auto_refresh_ms: 2000,
      })
    }
    if (url.pathname === '/api/docs/page') {
      const offset = Number(url.searchParams.get('offset') || 0)
      const limit = Number(url.searchParams.get('limit') || 20)
      if (offset >= 20) {
        return Promise.resolve({
          items: [
            {
              id: 'doc-page-2',
              user_id: 'test',
              kb_id: 'kb-1',
              filename: '第二页文档.pdf',
              file_type: 'pdf',
              num_chunks: 2,
              num_pages: 1,
              char_count: 100,
              status: 'ready',
              created_at: new Date('2026-02-22T10:00:00Z').toISOString(),
            },
          ],
          total: 25,
          offset,
          limit,
          has_more: false,
        })
      }
      return Promise.resolve({
        items: [
          {
            id: 'doc-page-1',
            user_id: 'test',
            kb_id: 'kb-1',
            filename: '第一页文档.pdf',
            file_type: 'pdf',
            num_chunks: 3,
            num_pages: 2,
            char_count: 200,
            status: 'ready',
            created_at: new Date('2026-02-22T09:00:00Z').toISOString(),
          },
        ],
        total: 25,
        offset,
        limit,
        has_more: true,
      })
    }
    return Promise.resolve({})
  })

  apiPost.mockResolvedValue({})
  apiPatch.mockResolvedValue({})
  apiDelete.mockResolvedValue({})
  apiUploadWithProgress.mockResolvedValue({})
})

describe('Upload pagination', () => {
  it('renders total count and loads next docs page when pager is clicked', async () => {
    const { wrapper, router } = await mountAppWithRouter()

    await router.push('/upload')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    expect(wrapper.text()).toContain('共 25 个')
    expect(wrapper.text()).toContain('第一页文档.pdf')
    expect(wrapper.text()).toContain('第 1 / 2 页')

    const nextBtn = wrapper.findAll('button').find((btn) => btn.text().trim() === '下一页')
    expect(nextBtn).toBeTruthy()
    await nextBtn.trigger('click')
    await flushPromises()
    await nextTick()
    await flushPromises()
    await nextTick()

    const pageCalls = apiGet.mock.calls
      .map(([path]) => parsePath(path))
      .filter((url) => url.pathname === '/api/docs/page')
    expect(pageCalls.some((url) => Number(url.searchParams.get('offset') || 0) === 20)).toBe(true)

    expect(wrapper.text()).toContain('第二页文档.pdf')
    expect(wrapper.text()).toContain('第 2 / 2 页')
  })
})

