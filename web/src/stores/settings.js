import { defineStore } from 'pinia'
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
} from '../api'

function deepClone(value) {
  return JSON.parse(JSON.stringify(value ?? null))
}

function deepMerge(base, patch) {
  const output = Array.isArray(base) ? [...base] : { ...(base || {}) }
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) return output
  for (const [key, value] of Object.entries(patch)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      output[key] = deepMerge(output[key] || {}, value)
    } else {
      output[key] = value
    }
  }
  return output
}

function normalizeUserSettingsShape(value = {}) {
  const qa = value?.qa || {}
  const quiz = value?.quiz || {}
  const ui = value?.ui || {}
  const upload = value?.upload || {}
  return {
    qa: {
      mode: qa.mode ?? 'normal',
      retrieval_preset: qa.retrieval_preset ?? 'balanced',
      top_k: qa.top_k ?? null,
      fetch_k: qa.fetch_k ?? null,
    },
    quiz: {
      count_default: Number.isFinite(Number(quiz.count_default)) ? Number(quiz.count_default) : 5,
      auto_adapt_default: typeof quiz.auto_adapt_default === 'boolean' ? quiz.auto_adapt_default : true,
      difficulty_default: quiz.difficulty_default ?? 'medium',
    },
    ui: {
      show_advanced_controls: typeof ui.show_advanced_controls === 'boolean' ? ui.show_advanced_controls : false,
      density: ui.density === 'compact' ? 'compact' : 'comfortable',
    },
    upload: {
      post_upload_suggestions: typeof upload.post_upload_suggestions === 'boolean' ? upload.post_upload_suggestions : true,
    },
  }
}

function normalizeKbSettingsShape(value = {}) {
  const qa = value?.qa || {}
  const quiz = value?.quiz || {}
  return {
    qa: {
      mode: qa.mode ?? null,
      retrieval_preset: qa.retrieval_preset ?? null,
      top_k: qa.top_k ?? null,
      fetch_k: qa.fetch_k ?? null,
    },
    quiz: {
      count_default: Number.isFinite(Number(quiz.count_default)) ? Number(quiz.count_default) : null,
      auto_adapt_default: typeof quiz.auto_adapt_default === 'boolean' ? quiz.auto_adapt_default : null,
      difficulty_default: quiz.difficulty_default ?? null,
    },
  }
}

function stableStringify(value) {
  return JSON.stringify(value ?? null)
}

function normalizeSystemSettingsShape(value = {}) {
  const editableKeys = Array.isArray(value?.editable_keys) ? [...value.editable_keys] : []
  const overrides = value?.overrides && typeof value.overrides === 'object' ? { ...value.overrides } : {}
  const effective = value?.effective && typeof value.effective === 'object' ? { ...value.effective } : {}
  const groups = Array.isArray(value?.schema?.groups)
    ? value.schema.groups
      .filter((item) => item && typeof item.id === 'string')
      .map((item) => ({ id: String(item.id), label: String(item.label || item.id) }))
    : []
  const fields = Array.isArray(value?.schema?.fields)
    ? value.schema.fields
      .filter((item) => item && typeof item.key === 'string')
      .map((item) => ({
        key: String(item.key),
        label: String(item.label || item.key),
        group: String(item.group || 'misc'),
        input_type: String(item.input_type || 'text'),
        nullable: Boolean(item.nullable),
        description: typeof item.description === 'string' ? item.description : '',
        options: Array.isArray(item.options)
          ? item.options.map((option) => ({
            value: option?.value,
            label: String(option?.label ?? option?.value ?? ''),
          }))
          : [],
        min: Number.isFinite(Number(item.min)) ? Number(item.min) : null,
        max: Number.isFinite(Number(item.max)) ? Number(item.max) : null,
        step: Number.isFinite(Number(item.step)) ? Number(item.step) : null,
      }))
    : []
  return {
    editableKeys,
    overrides,
    effective,
    schema: {
      groups,
      fields,
    },
  }
}

function normalizeProviderConfigShape(value = {}) {
  const effective = value?.effective || {}
  const deepseek = effective?.deepseek || {}
  const qwen = effective?.qwen || {}
  const dashscope = effective?.dashscope || {}
  const setup = value?.setup || {}
  return {
    editable: value?.editable !== false,
    readOnlyReason: typeof value?.read_only_reason === 'string' ? value.read_only_reason : '',
    supportedLlmProviders: Array.isArray(value?.supported_llm_providers)
      ? value.supported_llm_providers.map((item) => String(item))
      : ['auto', 'deepseek', 'qwen'],
    supportedEmbeddingProviders: Array.isArray(value?.supported_embedding_providers)
      ? value.supported_embedding_providers.map((item) => String(item))
      : ['auto', 'deepseek', 'qwen', 'dashscope'],
    regionPresets: {
      qwen: Array.isArray(value?.region_presets?.qwen)
        ? value.region_presets.qwen.map((item) => ({
          id: String(item?.id || 'custom'),
          label: String(item?.label || item?.id || '自定义'),
          base_url: typeof item?.base_url === 'string' ? item.base_url : null,
        }))
        : [],
      dashscope: Array.isArray(value?.region_presets?.dashscope)
        ? value.region_presets.dashscope.map((item) => ({
          id: String(item?.id || 'custom'),
          label: String(item?.label || item?.id || '自定义'),
          base_url: typeof item?.base_url === 'string' ? item.base_url : null,
        }))
        : [],
    },
    effective: {
      llm_provider: effective?.llm_provider ?? 'auto',
      embedding_provider: effective?.embedding_provider ?? 'auto',
      deepseek: {
        api_key_configured: Boolean(deepseek?.api_key_configured),
        api_key_masked: typeof deepseek?.api_key_masked === 'string' ? deepseek.api_key_masked : '',
        base_url: typeof deepseek?.base_url === 'string' ? deepseek.base_url : '',
        model: typeof deepseek?.model === 'string' ? deepseek.model : '',
        embedding_model: typeof deepseek?.embedding_model === 'string' ? deepseek.embedding_model : '',
      },
      qwen: {
        api_key_configured: Boolean(qwen?.api_key_configured),
        api_key_masked: typeof qwen?.api_key_masked === 'string' ? qwen.api_key_masked : '',
        region: typeof qwen?.region === 'string' ? qwen.region : 'custom',
        base_url: typeof qwen?.base_url === 'string' ? qwen.base_url : '',
        model: typeof qwen?.model === 'string' ? qwen.model : '',
        embedding_model: typeof qwen?.embedding_model === 'string' ? qwen.embedding_model : '',
      },
      dashscope: {
        region: typeof dashscope?.region === 'string' ? dashscope.region : 'china',
        base_url: typeof dashscope?.base_url === 'string' ? dashscope.base_url : '',
        embedding_model: typeof dashscope?.embedding_model === 'string' ? dashscope.embedding_model : '',
        using_shared_api_key: dashscope?.using_shared_api_key !== false,
      },
    },
    setup: {
      llm_ready: Boolean(setup?.llm_ready),
      embedding_ready: Boolean(setup?.embedding_ready),
      missing: Array.isArray(setup?.missing) ? setup.missing.map((item) => String(item)) : [],
      current_llm_provider: typeof setup?.current_llm_provider === 'string' ? setup.current_llm_provider : 'unconfigured',
      current_embedding_provider: typeof setup?.current_embedding_provider === 'string' ? setup.current_embedding_provider : 'unconfigured',
    },
  }
}

function buildProviderDraft(config = normalizeProviderConfigShape()) {
  const effective = config?.effective || {}
  const deepseek = effective?.deepseek || {}
  const qwen = effective?.qwen || {}
  const dashscope = effective?.dashscope || {}
  return {
    llm_provider: effective?.llm_provider ?? 'auto',
    embedding_provider: effective?.embedding_provider ?? 'auto',
    deepseek: {
      api_key_input: '',
      clear_api_key: false,
      editing_api_key: !deepseek?.api_key_configured,
      api_key_configured: Boolean(deepseek?.api_key_configured),
      api_key_masked: typeof deepseek?.api_key_masked === 'string' ? deepseek.api_key_masked : '',
      base_url: typeof deepseek?.base_url === 'string' ? deepseek.base_url : '',
      model: typeof deepseek?.model === 'string' ? deepseek.model : '',
      embedding_model: typeof deepseek?.embedding_model === 'string' ? deepseek.embedding_model : '',
    },
    qwen: {
      api_key_input: '',
      clear_api_key: false,
      editing_api_key: !qwen?.api_key_configured,
      api_key_configured: Boolean(qwen?.api_key_configured),
      api_key_masked: typeof qwen?.api_key_masked === 'string' ? qwen.api_key_masked : '',
      region: typeof qwen?.region === 'string' ? qwen.region : 'custom',
      base_url: typeof qwen?.base_url === 'string' ? qwen.base_url : '',
      model: typeof qwen?.model === 'string' ? qwen.model : '',
      embedding_model: typeof qwen?.embedding_model === 'string' ? qwen.embedding_model : '',
    },
    dashscope: {
      region: typeof dashscope?.region === 'string' ? dashscope.region : 'china',
      base_url: typeof dashscope?.base_url === 'string' ? dashscope.base_url : '',
      embedding_model: typeof dashscope?.embedding_model === 'string' ? dashscope.embedding_model : '',
    },
  }
}

function trimText(value) {
  return String(value ?? '').trim()
}

function buildProviderComparableShape(draft = {}) {
  return {
    llm_provider: draft?.llm_provider ?? 'auto',
    embedding_provider: draft?.embedding_provider ?? 'auto',
    deepseek: {
      base_url: trimText(draft?.deepseek?.base_url),
      model: trimText(draft?.deepseek?.model),
      embedding_model: trimText(draft?.deepseek?.embedding_model),
      api_key_action: draft?.deepseek?.clear_api_key ? 'clear' : (trimText(draft?.deepseek?.api_key_input) ? 'replace' : 'keep'),
    },
    qwen: {
      region: draft?.qwen?.region ?? 'custom',
      base_url: trimText(draft?.qwen?.base_url),
      model: trimText(draft?.qwen?.model),
      embedding_model: trimText(draft?.qwen?.embedding_model),
      api_key_action: draft?.qwen?.clear_api_key ? 'clear' : (trimText(draft?.qwen?.api_key_input) ? 'replace' : 'keep'),
    },
    dashscope: {
      region: draft?.dashscope?.region ?? 'china',
      base_url: trimText(draft?.dashscope?.base_url),
      embedding_model: trimText(draft?.dashscope?.embedding_model),
    },
  }
}

function buildProviderPatchPayload(draft = {}) {
  const payload = {
    llm_provider: draft?.llm_provider ?? 'auto',
    embedding_provider: draft?.embedding_provider ?? 'auto',
    deepseek: {
      base_url: trimText(draft?.deepseek?.base_url) || null,
      model: trimText(draft?.deepseek?.model) || null,
      embedding_model: trimText(draft?.deepseek?.embedding_model) || null,
    },
    qwen: {
      region: draft?.qwen?.region ?? 'custom',
      base_url: trimText(draft?.qwen?.base_url) || null,
      model: trimText(draft?.qwen?.model) || null,
      embedding_model: trimText(draft?.qwen?.embedding_model) || null,
    },
    dashscope: {
      region: draft?.dashscope?.region ?? 'china',
      base_url: trimText(draft?.dashscope?.base_url) || null,
      embedding_model: trimText(draft?.dashscope?.embedding_model) || null,
    },
  }

  const deepseekKey = trimText(draft?.deepseek?.api_key_input)
  if (draft?.deepseek?.clear_api_key) {
    payload.deepseek.clear_api_key = true
  } else if (deepseekKey) {
    payload.deepseek.api_key = deepseekKey
  }

  const qwenKey = trimText(draft?.qwen?.api_key_input)
  if (draft?.qwen?.clear_api_key) {
    payload.qwen.clear_api_key = true
  } else if (qwenKey) {
    payload.qwen.api_key = qwenKey
  }

  return payload
}

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    loading: false,
    savingUser: false,
    savingKb: false,
    savingSystem: false,
    resetting: false,
    providerSaving: false,
    providerTesting: false,
    error: '',

    loadedUserId: '',
    loadedKbId: '',

    systemStatus: null,
    meta: null,
    userDefaults: normalizeUserSettingsShape(),
    kbOverrides: null,
    effective: normalizeUserSettingsShape(),
    systemAdvanced: normalizeSystemSettingsShape(),
    systemAdvancedDraft: {},
    providerConfig: normalizeProviderConfigShape(),
    providerDraft: buildProviderDraft(),
    providerTestResult: null,

    userDraft: normalizeUserSettingsShape(),
    kbDraft: normalizeKbSettingsShape(),
  }),

  getters: {
    effectiveSettings(state) {
      return state.effective || normalizeUserSettingsShape()
    },
    userDirty(state) {
      return stableStringify(state.userDraft) !== stableStringify(state.userDefaults)
    },
    kbDirty(state) {
      const base = state.kbOverrides ? normalizeKbSettingsShape(state.kbOverrides) : normalizeKbSettingsShape()
      return stableStringify(state.kbDraft) !== stableStringify(base)
    },
    hasKbContext(state) {
      return Boolean(state.loadedKbId)
    },
    systemAdvancedDirty(state) {
      return stableStringify(state.systemAdvancedDraft) !== stableStringify(state.systemAdvanced.overrides)
    },
    providerDirty(state) {
      return stableStringify(buildProviderComparableShape(state.providerDraft))
        !== stableStringify(buildProviderComparableShape(buildProviderDraft(state.providerConfig)))
    },
    providerSetup(state) {
      return state.systemStatus?.provider_setup || state.providerConfig?.setup || null
    },
    llmFeaturesReady() {
      const setup = this.providerSetup
      if (!setup) return true
      return Boolean(setup.llm_ready && setup.embedding_ready)
    },
  },

  actions: {
    _applySystemSettingsResponse(response) {
      const normalized = normalizeSystemSettingsShape(response || {})
      this.systemAdvanced = normalized
      this.systemAdvancedDraft = deepClone(normalized.overrides) || {}
      return normalized
    },

    _applyProviderConfigResponse(response) {
      const normalized = normalizeProviderConfigShape(response || {})
      this.providerConfig = normalized
      this.providerDraft = buildProviderDraft(normalized)
      this.providerTestResult = null
      return normalized
    },

    _applyResponse(response, context = {}) {
      this.systemStatus = response?.system_status || null
      this.meta = response?.meta || null
      this.userDefaults = normalizeUserSettingsShape(response?.user_defaults || {})
      this.kbOverrides = response?.kb_overrides ? normalizeKbSettingsShape(response.kb_overrides) : null
      this.effective = normalizeUserSettingsShape(response?.effective || {})
      this.userDraft = normalizeUserSettingsShape(response?.user_defaults || {})
      this.kbDraft = response?.kb_overrides ? normalizeKbSettingsShape(response.kb_overrides) : normalizeKbSettingsShape()
      this.loadedUserId = String(context.userId || this.loadedUserId || '')
      this.loadedKbId = String(context.kbId || '')
      this.error = ''
      return response
    },

    setUserDraftSection(section, patch) {
      const next = deepMerge(this.userDraft[section] || {}, patch || {})
      this.userDraft = {
        ...this.userDraft,
        [section]: next,
      }
    },

    setKbDraftSection(section, patch) {
      const next = deepMerge(this.kbDraft[section] || {}, patch || {})
      this.kbDraft = {
        ...this.kbDraft,
        [section]: next,
      }
    },

    discardUserDraft() {
      this.userDraft = normalizeUserSettingsShape(this.userDefaults)
    },

    discardKbDraft() {
      this.kbDraft = this.kbOverrides ? normalizeKbSettingsShape(this.kbOverrides) : normalizeKbSettingsShape()
    },

    setSystemAdvancedDraft(value = {}) {
      this.systemAdvancedDraft = deepClone(value) || {}
    },

    setProviderDraft(patch = {}) {
      this.providerDraft = deepMerge(this.providerDraft || buildProviderDraft(this.providerConfig), patch || {})
    },

    discardSystemAdvancedDraft() {
      this.systemAdvancedDraft = deepClone(this.systemAdvanced.overrides) || {}
    },

    discardProviderDraft() {
      this.providerDraft = buildProviderDraft(this.providerConfig)
      this.providerTestResult = null
    },

    async load(options = {}) {
      const userId = options.userId || ''
      const kbId = options.kbId || ''
      const force = options.force === true

      if (!force && this.systemStatus && this.loadedUserId === String(userId || this.loadedUserId || '') && this.loadedKbId === String(kbId || '')) {
        return this
      }

      this.loading = true
      this.error = ''
      try {
        const [response, systemResponse, providerResponse] = await Promise.all([
          getSettings({ userId: userId || undefined, kbId: kbId || undefined }),
          getSystemSettings(),
          getSystemProviderSettings(),
        ])
        this._applyResponse(response, { userId, kbId })
        this._applySystemSettingsResponse(systemResponse)
        this._applyProviderConfigResponse(providerResponse)
        return this
      } catch (err) {
        this.error = err?.message || '加载设置失败'
        throw err
      } finally {
        this.loading = false
      }
    },

    async saveUser(userId = '') {
      this.savingUser = true
      this.error = ''
      try {
        const payload = { ...deepClone(this.userDraft) }
        if (userId) payload.user_id = userId
        const response = await patchUserSettings(payload)
        this._applyResponse(response, { userId, kbId: this.loadedKbId })
        return response
      } catch (err) {
        this.error = err?.message || '保存用户设置失败'
        throw err
      } finally {
        this.savingUser = false
      }
    },

    async saveKb(kbId, userId = '') {
      const targetKbId = String(kbId || this.loadedKbId || '').trim()
      if (!targetKbId) return null
      this.savingKb = true
      this.error = ''
      try {
        const payload = {
          qa: deepClone(this.kbDraft.qa),
          quiz: deepClone(this.kbDraft.quiz),
        }
        if (userId) payload.user_id = userId
        const response = await patchKbSettings(targetKbId, payload)
        this._applyResponse(response, { userId, kbId: targetKbId })
        return response
      } catch (err) {
        this.error = err?.message || '保存知识库设置失败'
        throw err
      } finally {
        this.savingKb = false
      }
    },

    async reset(scope, options = {}) {
      this.resetting = true
      this.error = ''
      try {
        const payload = { scope }
        if (options.userId) payload.user_id = options.userId
        if (scope === 'kb') payload.kb_id = options.kbId || this.loadedKbId
        if (scope === 'user' && (options.kbId || this.loadedKbId)) payload.kb_id = options.kbId || this.loadedKbId
        const response = await resetSettings(payload)
        this._applyResponse(response, { userId: options.userId, kbId: payload.kb_id || '' })
        return response
      } catch (err) {
        this.error = err?.message || '重置设置失败'
        throw err
      } finally {
        this.resetting = false
      }
    },

    async saveSystemAdvanced(values = null) {
      this.savingSystem = true
      this.error = ''
      try {
        const payloadValues = values && typeof values === 'object'
          ? deepClone(values)
          : deepClone(this.systemAdvancedDraft)
        const response = await patchSystemSettings({ values: payloadValues || {} })
        this._applySystemSettingsResponse(response)
        return response
      } catch (err) {
        this.error = err?.message || '保存系统高级设置失败'
        throw err
      } finally {
        this.savingSystem = false
      }
    },

    async resetSystemAdvanced(keys = null) {
      this.savingSystem = true
      this.error = ''
      try {
        const payload = keys && Array.isArray(keys) ? { keys } : {}
        const response = await resetSystemSettings(payload)
        this._applySystemSettingsResponse(response)
        return response
      } catch (err) {
        this.error = err?.message || '重置系统高级设置失败'
        throw err
      } finally {
        this.savingSystem = false
      }
    },

    async saveProviderConfig(values = null) {
      this.providerSaving = true
      this.error = ''
      try {
        const nextDraft = values && typeof values === 'object'
          ? deepClone(values)
          : deepClone(this.providerDraft)
        const response = await patchSystemProviderSettings({
          values: buildProviderPatchPayload(nextDraft || {}),
        })
        const settingsResponse = await getSettings({
          userId: this.loadedUserId || undefined,
          kbId: this.loadedKbId || undefined,
        })
        this._applyProviderConfigResponse(response)
        this._applyResponse(settingsResponse, { userId: this.loadedUserId, kbId: this.loadedKbId })
        return response
      } catch (err) {
        this.error = err?.message || '保存模型接入配置失败'
        throw err
      } finally {
        this.providerSaving = false
      }
    },

    async testProviderConfig(options = {}) {
      this.providerTesting = true
      this.error = ''
      try {
        const nextDraft = options.values && typeof options.values === 'object'
          ? deepClone(options.values)
          : deepClone(this.providerDraft)
        const response = await testSystemProviderSettings({
          values: buildProviderPatchPayload(nextDraft || {}),
          target: options.target || 'auto',
        })
        this.providerTestResult = response
        return response
      } catch (err) {
        this.error = err?.message || '测试模型接入配置失败'
        throw err
      } finally {
        this.providerTesting = false
      }
    },
  },
})
