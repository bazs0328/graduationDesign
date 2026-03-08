function isObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value)
}

function deepMerge(base, patch) {
  if (!isObject(base)) return isObject(patch) ? { ...patch } : patch
  const next = { ...base }
  if (!isObject(patch)) return next
  for (const [key, value] of Object.entries(patch)) {
    if (isObject(value) && isObject(next[key])) {
      next[key] = deepMerge(next[key], value)
    } else {
      next[key] = value
    }
  }
  return next
}

export function buildProviderSetup(overrides = {}) {
  return deepMerge(
    {
      llm_ready: true,
      embedding_ready: true,
      missing: [],
      current_llm_provider: 'qwen',
      current_embedding_provider: 'dashscope',
    },
    overrides,
  )
}

export function buildSettingsResponse(overrides = {}) {
  const base = {
    system_status: {
      llm_provider: 'qwen',
      embedding_provider: 'dashscope',
      llm_provider_configured: 'qwen',
      embedding_provider_configured: 'dashscope',
      llm_provider_source: 'manual',
      embedding_provider_source: 'manual',
      qa_defaults: { qa_top_k: 4, qa_fetch_k: 12, qa_dynamic_window_enabled: true, rag_mode: 'hybrid' },
      ocr_enabled: true,
      pdf_parser_mode: 'auto',
      auth_require_login: true,
      secrets_configured: { qwen_api_key: true },
      notices: [],
      version_info: { app_name: 'StudyCompass' },
      provider_setup: buildProviderSetup(),
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
  return deepMerge(base, overrides)
}

export function buildSystemSettingsResponse(overrides = {}) {
  return deepMerge(
    {
      editable_keys: [],
      overrides: {},
      effective: {},
      schema: {
        groups: [],
        fields: [],
      },
    },
    overrides,
  )
}

export function buildProviderConfigResponse(overrides = {}) {
  const base = {
    editable: true,
    read_only_reason: '',
    supported_llm_providers: ['auto', 'deepseek', 'qwen'],
    supported_embedding_providers: ['auto', 'qwen', 'dashscope'],
    region_presets: {
      qwen: [
        { id: 'china', label: '中国站', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
        { id: 'international', label: '国际站', base_url: 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1' },
        { id: 'custom', label: '自定义', base_url: null },
      ],
      dashscope: [
        { id: 'china', label: '中国站', base_url: 'https://dashscope.aliyuncs.com/api/v1' },
        { id: 'international', label: '国际站', base_url: 'https://dashscope-intl.aliyuncs.com/api/v1' },
        { id: 'custom', label: '自定义', base_url: null },
      ],
    },
    effective: {
      llm_provider: 'qwen',
      embedding_provider: 'dashscope',
      deepseek: {
        api_key_configured: false,
        api_key_masked: '',
        base_url: 'https://api.deepseek.com/v1',
        model: 'deepseek-chat',
      },
      qwen: {
        api_key_configured: true,
        api_key_masked: '••••abcd',
        region: 'china',
        base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        model: 'qwen-max',
        embedding_model: 'text-embedding-v4',
      },
      dashscope: {
        region: 'china',
        base_url: 'https://dashscope.aliyuncs.com/api/v1',
        embedding_model: 'text-embedding-v4',
        using_shared_api_key: true,
      },
    },
    setup: buildProviderSetup(),
  }
  return deepMerge(base, overrides)
}
