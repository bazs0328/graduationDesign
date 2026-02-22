import { defineStore } from 'pinia'
import { apiGet } from '../api'
import { normalizeQueryString, parseRouteContext } from '../utils/routeContext'

export const APP_CONTEXT_KEY_PREFIX = 'gradtutor_app_ctx_v1:'

const EMPTY_ROUTE_CONTEXT = {
  focus: '',
  difficulty: '',
  keypointText: '',
}

const kbsInFlightByUser = new Map()

function resolveUserIdFromStorage() {
  return (
    localStorage.getItem('gradtutor_user')
    || localStorage.getItem('gradtutor_user_id')
    || 'default'
  )
}

function storageKeyForUser(userId) {
  const normalized = normalizeQueryString(userId) || 'default'
  return `${APP_CONTEXT_KEY_PREFIX}${normalized}`
}

function readPersistedContext(userId) {
  try {
    const raw = localStorage.getItem(storageKeyForUser(userId))
    if (!raw) {
      return { selectedKbId: '', selectedDocId: '' }
    }
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') {
      return { selectedKbId: '', selectedDocId: '' }
    }
    return {
      selectedKbId: normalizeQueryString(parsed.selectedKbId),
      selectedDocId: normalizeQueryString(parsed.selectedDocId),
    }
  } catch {
    return { selectedKbId: '', selectedDocId: '' }
  }
}

function writePersistedContext(userId, payload) {
  try {
    const data = {
      selectedKbId: normalizeQueryString(payload?.selectedKbId),
      selectedDocId: normalizeQueryString(payload?.selectedDocId),
    }
    localStorage.setItem(storageKeyForUser(userId), JSON.stringify(data))
  } catch {
    // ignore storage write failures
  }
}

export const useAppContextStore = defineStore('appContext', {
  state: () => ({
    resolvedUserId: 'default',
    kbs: [],
    kbsUserId: '',
    kbsLoading: false,
    selectedKbId: '',
    selectedDocId: '',
    routeContext: { ...EMPTY_ROUTE_CONTEXT },
  }),

  actions: {
    hydrate() {
      const nextUserId = resolveUserIdFromStorage()
      const userChanged = nextUserId !== this.resolvedUserId

      this.resolvedUserId = nextUserId

      if (userChanged) {
        this.kbs = []
        this.kbsUserId = ''
        this.kbsLoading = false
        this.routeContext = { ...EMPTY_ROUTE_CONTEXT }
      }

      const persisted = readPersistedContext(nextUserId)
      this.selectedKbId = persisted.selectedKbId
      this.selectedDocId = persisted.selectedDocId
      return this
    },

    persistSelection() {
      writePersistedContext(this.resolvedUserId, {
        selectedKbId: this.selectedKbId,
        selectedDocId: this.selectedDocId,
      })
    },

    setSelectedKbId(kbId) {
      const nextKbId = normalizeQueryString(kbId)
      const previousKbId = this.selectedKbId
      if (previousKbId === nextKbId) return

      this.selectedKbId = nextKbId
      if (!nextKbId || previousKbId !== nextKbId) {
        this.selectedDocId = ''
      }
      this.persistSelection()
    },

    setSelectedDocId(docId) {
      const nextDocId = normalizeQueryString(docId)
      if (this.selectedDocId === nextDocId) return
      this.selectedDocId = nextDocId
      this.persistSelection()
    },

    syncSelectionWithKbs() {
      if (!Array.isArray(this.kbs) || this.kbs.length === 0) {
        if (this.selectedKbId || this.selectedDocId) {
          this.selectedKbId = ''
          this.selectedDocId = ''
          this.persistSelection()
        }
        return
      }

      const hasSelectedKb = this.selectedKbId && this.kbs.some((kb) => kb.id === this.selectedKbId)
      if (!hasSelectedKb) {
        this.selectedKbId = this.kbs[0]?.id || ''
        this.selectedDocId = ''
        this.persistSelection()
      }
    },

    async loadKbs(force = false) {
      const userId = this.resolvedUserId || 'default'

      if (!force && this.kbsUserId === userId && this.kbs.length) {
        return this.kbs
      }

      const existingRequest = kbsInFlightByUser.get(userId)
      if (existingRequest) {
        return existingRequest
      }

      this.kbsLoading = true

      const request = apiGet(`/api/kb?user_id=${encodeURIComponent(userId)}`)
        .then((rows) => {
          this.kbs = Array.isArray(rows) ? rows : []
          this.kbsUserId = userId
          this.syncSelectionWithKbs()
          return this.kbs
        })
        .finally(() => {
          if (kbsInFlightByUser.get(userId) === request) {
            kbsInFlightByUser.delete(userId)
          }
          this.kbsLoading = false
        })

      kbsInFlightByUser.set(userId, request)
      return request
    },

    async applyRouteContext(query, options = {}) {
      const parsed = parseRouteContext(query)

      this.routeContext = {
        focus: parsed.focus,
        difficulty: parsed.difficulty,
        keypointText: parsed.keypointText,
      }

      if (options.ensureKbs) {
        await this.loadKbs(options.forceKbs === true)
      }

      if (parsed.kbId) {
        this.setSelectedKbId(parsed.kbId)
      } else if (options.fallbackToFirstKb && this.kbs.length && !this.selectedKbId) {
        this.setSelectedKbId(this.kbs[0]?.id || '')
      }

      if (parsed.docId) {
        this.setSelectedDocId(parsed.docId)
      } else if (options.clearDocIfMissing) {
        this.setSelectedDocId('')
      }

      return parsed
    },

    clearContext() {
      this.selectedKbId = ''
      this.selectedDocId = ''
      this.routeContext = { ...EMPTY_ROUTE_CONTEXT }
      this.kbs = []
      this.kbsUserId = ''
      this.kbsLoading = false
      this.persistSelection()
    },
  },
})
