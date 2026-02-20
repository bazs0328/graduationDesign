import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import Upload from '@/views/Upload.vue'
import { apiDelete, apiGet, apiPatch, apiPost } from '@/api'

vi.mock('@/api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    apiPatch: vi.fn(),
    apiDelete: vi.fn()
  }
})

const kbFixture = { id: 'kb-1', name: '默认知识库' }

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

async function mountUpload() {
  localStorage.setItem('gradtutor_user', 'user_test')
  const wrapper = mount(Upload, {
    attachTo: document.body
  })
  await flushPromises()
  await nextTick()
  await nextTick()
  return wrapper
}

function mockApi({
  docs = [],
  tasks = null,
  diagnostics = null
} = {}) {
  apiGet.mockImplementation((path) => {
    if (path.startsWith('/api/kb?')) return Promise.resolve([kbFixture])
    if (path.startsWith('/api/kb/kb-1/settings')) {
      return Promise.resolve({ kb_id: 'kb-1', parse_policy: 'balanced', preferred_parser: 'auto' })
    }
    if (path.startsWith('/api/docs/tasks')) {
      return Promise.resolve(tasks || {
        processing: [],
        error: [],
        processing_count: 0,
        error_count: 0,
        stage_counts: {},
        avg_progress_percent: 0,
        running_workers: 0,
        queued_jobs: 0,
        auto_refresh_ms: 2000
      })
    }
    if (path.startsWith('/api/docs/') && path.includes('/diagnostics')) {
      return Promise.resolve(diagnostics || {
        parser_provider: 'native',
        extract_method: 'hybrid',
        strategy: 'selective_ocr',
        quality_score: 71.2,
        low_quality_pages: [2],
        ocr_pages: [2],
        page_scores: [],
        stage_timings_ms: { extract: 12.3, ocr: 18.5 }
      })
    }
    if (path.startsWith('/api/docs?')) return Promise.resolve(docs)
    return Promise.resolve({})
  })

  apiPost.mockImplementation((path) => {
    if (path === '/api/docs/retry-failed') {
      return Promise.resolve({ queued: ['doc-error'], skipped: [] })
    }
    return Promise.resolve({})
  })
  apiPatch.mockResolvedValue({})
  apiDelete.mockResolvedValue({})
}

beforeEach(() => {
  localStorage.clear()
  apiGet.mockReset()
  apiPost.mockReset()
  apiPatch.mockReset()
  apiDelete.mockReset()
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('Upload task center', () => {
  it('renders stage progress and task center stats', async () => {
    mockApi({
      docs: [
        {
          id: 'doc-processing',
          user_id: 'user_test',
          kb_id: 'kb-1',
          filename: 'scan.pdf',
          file_type: 'pdf',
          num_chunks: 0,
          num_pages: 0,
          char_count: 0,
          status: 'processing',
          stage: 'ocr',
          progress_percent: 40,
          parser_provider: null,
          extract_method: null,
          quality_score: null,
          created_at: new Date().toISOString()
        }
      ],
      tasks: {
        processing: [
          {
            id: 'doc-processing',
            user_id: 'user_test',
            kb_id: 'kb-1',
            filename: 'scan.pdf',
            file_type: 'pdf',
            num_chunks: 0,
            num_pages: 0,
            char_count: 0,
            status: 'processing',
            stage: 'ocr',
            progress_percent: 40,
            created_at: new Date().toISOString()
          }
        ],
        error: [],
        processing_count: 1,
        error_count: 0,
        stage_counts: { ocr: 1 },
        avg_progress_percent: 40,
        running_workers: 1,
        queued_jobs: 2,
        auto_refresh_ms: 2000
      }
    })

    const wrapper = await mountUpload()
    const text = wrapper.text()
    expect(text).toContain('OCR')
    expect(text).toContain('40%')
    expect(text).toContain('运行中 1')
    expect(text).toContain('排队 2')
    expect(text).toContain('平均进度 40.0%')
    wrapper.unmount()
  })

  it('sends selected retry mode when retrying failed tasks', async () => {
    mockApi({
      docs: [
        {
          id: 'doc-error',
          user_id: 'user_test',
          kb_id: 'kb-1',
          filename: 'bad.pdf',
          file_type: 'pdf',
          num_chunks: 0,
          num_pages: 0,
          char_count: 0,
          status: 'error',
          error_message: 'extract failed',
          created_at: new Date().toISOString()
        }
      ],
      tasks: {
        processing: [],
        error: [
          {
            id: 'doc-error',
            user_id: 'user_test',
            kb_id: 'kb-1',
            filename: 'bad.pdf',
            file_type: 'pdf',
            num_chunks: 0,
            num_pages: 0,
            char_count: 0,
            status: 'error',
            error_message: 'extract failed',
            created_at: new Date().toISOString()
          }
        ],
        processing_count: 0,
        error_count: 1,
        stage_counts: {},
        avg_progress_percent: 0,
        running_workers: 0,
        queued_jobs: 0,
        auto_refresh_ms: 2000
      }
    })

    const wrapper = await mountUpload()
    await wrapper.get('[data-testid="process-mode-select"]').setValue('force_ocr')
    await wrapper.get('[data-testid="retry-failed-btn"]').trigger('click')
    await flushPromises()
    await nextTick()

    expect(apiPost).toHaveBeenCalledWith(
      '/api/docs/retry-failed',
      expect.objectContaining({
        mode: 'force_ocr'
      })
    )
    wrapper.unmount()
  })

  it('opens diagnostics modal and renders payload', async () => {
    mockApi({
      docs: [
        {
          id: 'doc-ready',
          user_id: 'user_test',
          kb_id: 'kb-1',
          filename: 'ready.pdf',
          file_type: 'pdf',
          num_chunks: 10,
          num_pages: 3,
          char_count: 8000,
          status: 'ready',
          stage: 'done',
          progress_percent: 100,
          parser_provider: 'native',
          extract_method: 'hybrid',
          quality_score: 71.2,
          created_at: new Date().toISOString()
        }
      ]
    })

    const wrapper = await mountUpload()
    await wrapper.get('[data-testid="doc-diagnostics-btn"]').trigger('click')
    await flushPromises()
    await nextTick()

    const bodyText = document.body.textContent || ''
    expect(bodyText).toContain('文档诊断')
    expect(bodyText).toContain('selective_ocr')
    wrapper.unmount()
  })
})
