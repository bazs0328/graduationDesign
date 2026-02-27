import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

vi.mock('../../src/api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    apiGet: vi.fn(),
    getSettings: vi.fn(),
    getSystemSettings: vi.fn(),
    patchUserSettings: vi.fn(),
    patchKbSettings: vi.fn(),
    resetSettings: vi.fn(),
  }
})

import { apiGet, getSettings, getSystemSettings } from '../../src/api'
import SettingsView from '../../src/views/Settings.vue'

function buildSettingsResponse() {
  return {
    system_status: {
      llm_provider: 'qwen',
      embedding_provider: 'dashscope',
      llm_provider_configured: 'auto',
      embedding_provider_configured: 'auto',
      llm_provider_source: 'auto',
      embedding_provider_source: 'auto',
      qa_defaults_from_env: { qa_top_k: 4, qa_fetch_k: 12, rag_mode: 'hybrid' },
      ocr_enabled: true,
      pdf_parser_mode: 'auto',
      auth_require_login: true,
      secrets_configured: { qwen_api_key: true },
      version_info: { app_name: 'GradTutor' },
    },
    user_defaults: {
      qa: { mode: 'normal', retrieval_preset: 'balanced', top_k: null, fetch_k: null },
      quiz: { count_default: 5, auto_adapt_default: true, difficulty_default: 'medium' },
      ui: { show_advanced_controls: false, density: 'comfortable' },
      upload: { post_upload_suggestions: true },
    },
    kb_overrides: null,
    effective: {
      qa: { mode: 'normal', retrieval_preset: 'balanced', top_k: 4, fetch_k: 12 },
      quiz: { count_default: 5, auto_adapt_default: true, difficulty_default: 'medium' },
      ui: { show_advanced_controls: false, density: 'comfortable' },
      upload: { post_upload_suggestions: true },
    },
    meta: {
      qa_modes: ['normal', 'explain'],
      retrieval_presets: ['fast', 'balanced', 'deep'],
      quiz_difficulty_options: ['easy', 'medium', 'hard'],
      preset_map: {
        fast: { top_k: 3, fetch_k: 8 },
        balanced: { top_k: 4, fetch_k: 12 },
        deep: { top_k: 6, fetch_k: 20 },
      },
      ranges: { qa: { top_k_min: 1, top_k_max: 20, fetch_k_min: 1, fetch_k_max: 50 } },
      defaults: {},
    },
  }
}

function buildSystemSettingsResponse() {
  return {
    editable_keys: ['qa_top_k', 'rag_mode', 'ocr_enabled'],
    overrides: {},
    effective: { qa_top_k: 4, rag_mode: 'hybrid', ocr_enabled: true },
    schema: {
      groups: [
        { id: 'retrieval', label: '检索与召回' },
        { id: 'ocr', label: 'OCR 识别' },
      ],
      fields: [
        {
          key: 'qa_top_k',
          label: '问答参考片段数量',
          group: 'retrieval',
          input_type: 'number',
          nullable: false,
          options: [],
          min: 1,
          max: 20,
          step: 1,
        },
        {
          key: 'rag_mode',
          label: '检索策略',
          group: 'retrieval',
          input_type: 'select',
          nullable: false,
          options: [
            { value: 'hybrid', label: '混合（向量+词法）' },
            { value: 'dense', label: '纯向量' },
          ],
        },
        {
          key: 'ocr_enabled',
          label: '启用 OCR',
          group: 'ocr',
          input_type: 'switch',
          nullable: false,
          options: [],
        },
      ],
    },
  }
}

async function flush() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

describe('settings view simplification', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('gradtutor_user', 'view-test-user')
    localStorage.setItem('gradtutor_user_id', 'view-test-user')

    apiGet.mockImplementation((path) => {
      if (path.startsWith('/api/kb')) {
        return Promise.resolve([{ id: 'kb-1', name: '默认知识库' }])
      }
      return Promise.resolve([])
    })
    getSettings.mockResolvedValue(buildSettingsResponse())
    getSystemSettings.mockResolvedValue(buildSystemSettingsResponse())
  })

  it('hides technical diagnostics by default and reveals them when expanded', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(SettingsView, {
      global: {
        plugins: [pinia],
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await flush()

    const initialText = wrapper.text()
    expect(initialText).not.toContain('RAG')
    expect(initialText).not.toContain('top_k')
    expect(initialText).not.toContain('fetch_k')
    expect(initialText).not.toContain('检索向量模型（高级）')
    expect(initialText).not.toContain('当前知识库覆盖设置')

    const toggleBtn = wrapper
      .findAll('button')
      .find((btn) => btn.text().includes('展开高级诊断'))
    expect(toggleBtn).toBeTruthy()
    await toggleBtn.trigger('click')
    await flush()

    const expandedText = wrapper.text()
    expect(expandedText).toContain('检索向量模型（高级）')
    expect(expandedText).toContain('当前知识库覆盖设置')
    expect(expandedText).toContain('系统高级参数（可编辑）')
    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.findAll('input[type="number"]').length).toBeGreaterThan(0)
    expect(wrapper.findAll('select').length).toBeGreaterThan(1)
  })
})
