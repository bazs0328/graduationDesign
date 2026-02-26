import { defineStore } from 'pinia'
import { getSettings, patchKbSettings, patchUserSettings, resetSettings } from '../api'

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

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    loading: false,
    savingUser: false,
    savingKb: false,
    resetting: false,
    error: '',

    loadedUserId: '',
    loadedKbId: '',

    systemStatus: null,
    meta: null,
    userDefaults: normalizeUserSettingsShape(),
    kbOverrides: null,
    effective: normalizeUserSettingsShape(),

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
  },

  actions: {
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
        const response = await getSettings({ userId: userId || undefined, kbId: kbId || undefined })
        this._applyResponse(response, { userId, kbId })
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
  },
})
