import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../src/api', () => ({
  getSettings: vi.fn(),
  getSystemProviderSettings: vi.fn(),
  getSystemSettings: vi.fn(),
  patchKbSettings: vi.fn(),
  patchSystemProviderSettings: vi.fn(),
  patchSystemSettings: vi.fn(),
  patchUserSettings: vi.fn(),
  resetSettings: vi.fn(),
  resetSystemSettings: vi.fn(),
  testSystemProviderSettings: vi.fn(),
}))

import {
  getSettings,
  getSystemProviderSettings,
  getSystemSettings,
  patchKbSettings,
  patchSystemProviderSettings,
  patchSystemSettings,
  patchUserSettings,
  resetSettings,
  resetSystemSettings,
  testSystemProviderSettings,
} from '../../src/api'
import { useSettingsStore } from '../../src/stores/settings'
import {
  buildProviderConfigResponse,
  buildSettingsResponse,
  buildSystemSettingsResponse,
} from './fixtures/settingsFixtures'

describe('settings store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    getSystemProviderSettings.mockResolvedValue(buildProviderConfigResponse())
  })

  it('loads settings and tracks dirty state for user defaults save', async () => {
    getSettings.mockResolvedValueOnce(buildSettingsResponse())
    getSystemSettings.mockResolvedValueOnce(buildSystemSettingsResponse({
      editable_keys: ['qa_top_k', 'qa_fetch_k', 'rag_mode', 'ocr_enabled'],
      overrides: { qa_top_k: 4, qa_fetch_k: 12, rag_mode: 'hybrid' },
      effective: { qa_top_k: 4, qa_fetch_k: 12, rag_mode: 'hybrid', ocr_enabled: true },
    }))
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
    getSystemSettings.mockResolvedValueOnce(buildSystemSettingsResponse({
      editable_keys: ['qa_top_k', 'qa_fetch_k', 'rag_mode', 'ocr_enabled'],
      overrides: { qa_top_k: 4, qa_fetch_k: 12, rag_mode: 'hybrid' },
      effective: { qa_top_k: 4, qa_fetch_k: 12, rag_mode: 'hybrid', ocr_enabled: true },
    }))
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
    getSystemSettings.mockResolvedValueOnce(buildSystemSettingsResponse({
      editable_keys: ['qa_top_k', 'qa_fetch_k', 'rag_mode', 'ocr_enabled'],
      overrides: { qa_top_k: 4, qa_fetch_k: 12, rag_mode: 'hybrid' },
      effective: { qa_top_k: 4, qa_fetch_k: 12, rag_mode: 'hybrid', ocr_enabled: true },
    }))
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

  it('loads, saves, and tests provider config without exposing plaintext keys', async () => {
    getSettings.mockResolvedValueOnce(buildSettingsResponse())
    getSystemSettings.mockResolvedValueOnce(buildSystemSettingsResponse())
    patchSystemProviderSettings.mockResolvedValueOnce(
      buildProviderConfigResponse({
        effective: {
          qwen: {
            api_key_configured: true,
            api_key_masked: '••••9999',
            region: 'international',
            base_url: 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1',
            model: 'qwen-plus',
          },
        },
      }),
    )
    getSettings.mockResolvedValueOnce(
      buildSettingsResponse({
        system_status: {
          provider_setup: {
            llm_ready: true,
            embedding_ready: true,
            missing: [],
            current_llm_provider: 'qwen',
            current_embedding_provider: 'dashscope',
          },
        },
      }),
    )
    testSystemProviderSettings.mockResolvedValueOnce({
      ok: true,
      provider: 'qwen',
      target: 'llm',
      message: '连接成功',
    })

    const store = useSettingsStore()
    await store.load({ userId: 'user-a', kbId: 'kb-1' })

    store.setProviderDraft({
      llm_provider: 'qwen',
      qwen: {
        api_key_input: 'sk-test-9999',
        region: 'international',
        base_url: 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1',
        model: 'qwen-plus',
      },
    })
    expect(store.providerDirty).toBe(true)

    await store.testProviderConfig({ target: 'llm' })
    expect(testSystemProviderSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        target: 'llm',
        values: expect.objectContaining({
          llm_provider: 'qwen',
          qwen: expect.objectContaining({
            api_key: 'sk-test-9999',
            region: 'international',
          }),
        }),
      }),
    )

    await store.saveProviderConfig()
    expect(patchSystemProviderSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        values: expect.objectContaining({
          llm_provider: 'qwen',
          qwen: expect.objectContaining({
            api_key: 'sk-test-9999',
            region: 'international',
          }),
        }),
      }),
    )
    expect(store.providerConfig.effective.qwen.api_key_masked).toBe('••••9999')
    expect(store.providerDraft.qwen.api_key_input).toBe('')
    expect(store.providerDirty).toBe(false)
  })
})
