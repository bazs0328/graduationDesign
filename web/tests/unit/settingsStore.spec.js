import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../src/api', () => ({
  getSettings: vi.fn(),
  getSystemSettings: vi.fn(),
  patchKbSettings: vi.fn(),
  patchSystemSettings: vi.fn(),
  patchUserSettings: vi.fn(),
  resetSettings: vi.fn(),
  resetSystemSettings: vi.fn(),
}))

import {
  getSettings,
  getSystemSettings,
  patchKbSettings,
  patchSystemSettings,
  patchUserSettings,
  resetSettings,
  resetSystemSettings,
} from '../../src/api'
import { useSettingsStore } from '../../src/stores/settings'

function buildSettingsResponse(overrides = {}) {
  return {
    system_status: {
      llm_provider: 'qwen',
      embedding_provider: 'dashscope',
      llm_provider_configured: 'qwen',
      embedding_provider_configured: 'dashscope',
      llm_provider_source: 'manual',
      embedding_provider_source: 'manual',
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
    ...overrides,
  }
}

function buildSystemSettingsResponse(overrides = {}) {
  return {
    editable_keys: ['qa_top_k', 'qa_fetch_k', 'rag_mode', 'ocr_enabled'],
    overrides: { qa_top_k: 4, qa_fetch_k: 12, rag_mode: 'hybrid' },
    effective: { qa_top_k: 4, qa_fetch_k: 12, rag_mode: 'hybrid', ocr_enabled: true },
    ...overrides,
  }
}

describe('settings store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('loads settings and tracks dirty state for user defaults save', async () => {
    getSettings.mockResolvedValueOnce(buildSettingsResponse())
    getSystemSettings.mockResolvedValueOnce(buildSystemSettingsResponse())
    patchUserSettings.mockResolvedValueOnce(
      buildSettingsResponse({
        user_defaults: {
          qa: { mode: 'explain', retrieval_preset: 'balanced', top_k: null, fetch_k: null },
          quiz: { count_default: 5, auto_adapt_default: true, difficulty_default: 'medium' },
          ui: { show_advanced_controls: false, density: 'comfortable' },
          upload: { post_upload_suggestions: true },
        },
        effective: {
          qa: { mode: 'explain', retrieval_preset: 'balanced', top_k: 4, fetch_k: 12 },
          quiz: { count_default: 5, auto_adapt_default: true, difficulty_default: 'medium' },
          ui: { show_advanced_controls: false, density: 'comfortable' },
          upload: { post_upload_suggestions: true },
        },
      })
    )

    const store = useSettingsStore()
    await store.load({ userId: 'user-a', kbId: 'kb-1' })

    expect(store.loadedUserId).toBe('user-a')
    expect(store.loadedKbId).toBe('kb-1')
    expect(store.effectiveSettings.qa.top_k).toBe(4)
    expect(store.userDirty).toBe(false)

    store.setUserDraftSection('qa', { mode: 'explain' })
    expect(store.userDirty).toBe(true)

    await store.saveUser('user-a')

    expect(patchUserSettings).toHaveBeenCalledTimes(1)
    expect(patchUserSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        user_id: 'user-a',
        qa: expect.objectContaining({ mode: 'explain' }),
      })
    )
    expect(store.userDefaults.qa.mode).toBe('explain')
    expect(store.userDirty).toBe(false)
  })

  it('saves kb overrides with qa/quiz payload only and can reset kb scope', async () => {
    getSystemSettings.mockResolvedValueOnce(buildSystemSettingsResponse())
    getSettings.mockResolvedValueOnce(
      buildSettingsResponse({
        kb_overrides: {
          qa: { mode: 'normal', retrieval_preset: null, top_k: null, fetch_k: null },
          quiz: { count_default: null, auto_adapt_default: null, difficulty_default: null },
        },
      })
    )
    patchKbSettings.mockResolvedValueOnce(
      buildSettingsResponse({
        kb_overrides: {
          qa: { mode: 'explain', retrieval_preset: null, top_k: null, fetch_k: null },
          quiz: { count_default: 8, auto_adapt_default: false, difficulty_default: 'hard' },
        },
      })
    )
    resetSettings.mockResolvedValueOnce(buildSettingsResponse({ kb_overrides: null }))

    const store = useSettingsStore()
    await store.load({ userId: 'user-a', kbId: 'kb-1' })

    store.setKbDraftSection('qa', { mode: 'explain' })
    store.setKbDraftSection('quiz', { count_default: 8, auto_adapt_default: false, difficulty_default: 'hard' })
    expect(store.kbDirty).toBe(true)

    await store.saveKb('kb-1', 'user-a')
    expect(patchKbSettings).toHaveBeenCalledWith(
      'kb-1',
      expect.objectContaining({
        user_id: 'user-a',
        qa: expect.any(Object),
        quiz: expect.any(Object),
      })
    )
    expect(store.kbOverrides?.qa?.mode).toBe('explain')

    await store.reset('kb', { userId: 'user-a', kbId: 'kb-1' })
    expect(resetSettings).toHaveBeenCalledWith(
      expect.objectContaining({ scope: 'kb', user_id: 'user-a', kb_id: 'kb-1' })
    )
  })

  it('saves and resets system advanced overrides', async () => {
    getSettings.mockResolvedValueOnce(buildSettingsResponse())
    getSystemSettings.mockResolvedValueOnce(buildSystemSettingsResponse())
    patchSystemSettings.mockResolvedValueOnce(
      buildSystemSettingsResponse({
        overrides: { qa_top_k: 6, rag_mode: 'dense' },
        effective: { qa_top_k: 6, qa_fetch_k: 12, rag_mode: 'dense', ocr_enabled: true },
      })
    )
    resetSystemSettings.mockResolvedValueOnce(
      buildSystemSettingsResponse({
        overrides: {},
        effective: { qa_top_k: 4, qa_fetch_k: 12, rag_mode: 'hybrid', ocr_enabled: true },
      })
    )

    const store = useSettingsStore()
    await store.load({ userId: 'user-a', kbId: 'kb-1' })

    store.setSystemAdvancedDraft({ qa_top_k: 6, rag_mode: 'dense' })
    expect(store.systemAdvancedDirty).toBe(true)

    await store.saveSystemAdvanced()
    expect(patchSystemSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        values: expect.objectContaining({ qa_top_k: 6, rag_mode: 'dense' }),
      })
    )
    expect(store.systemAdvanced.overrides.qa_top_k).toBe(6)
    expect(store.systemAdvancedDirty).toBe(false)

    await store.resetSystemAdvanced()
    expect(resetSystemSettings).toHaveBeenCalledWith({})
    expect(store.systemAdvanced.overrides).toEqual({})
  })
})
