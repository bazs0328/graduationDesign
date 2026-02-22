import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    apiGet: vi.fn(),
  }
})

import { apiGet, logout } from '@/api'
import { APP_CONTEXT_KEY_PREFIX, useAppContextStore } from '@/stores/appContext'

function persistedKey(userId) {
  return `${APP_CONTEXT_KEY_PREFIX}${userId}`
}

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

describe('app context store', () => {
  beforeEach(() => {
    localStorage.clear()
    apiGet.mockReset()
    setActivePinia(createPinia())
  })

  it('hydrates persisted context by user id', () => {
    localStorage.setItem('gradtutor_user', 'user-a')
    localStorage.setItem(
      persistedKey('user-a'),
      JSON.stringify({ selectedKbId: 'kb-a', selectedDocId: 'doc-a' })
    )

    const store = useAppContextStore()
    store.hydrate()

    expect(store.resolvedUserId).toBe('user-a')
    expect(store.selectedKbId).toBe('kb-a')
    expect(store.selectedDocId).toBe('doc-a')
  })

  it('falls back to first kb when persisted kb is invalid', async () => {
    localStorage.setItem('gradtutor_user', 'user-a')
    localStorage.setItem(
      persistedKey('user-a'),
      JSON.stringify({ selectedKbId: 'missing-kb', selectedDocId: 'doc-old' })
    )
    apiGet.mockResolvedValue([
      { id: 'kb-1', name: 'KB 1' },
      { id: 'kb-2', name: 'KB 2' },
    ])

    const store = useAppContextStore()
    store.hydrate()
    await store.loadKbs(true)

    expect(store.selectedKbId).toBe('kb-1')
    expect(store.selectedDocId).toBe('')
  })

  it('lets route query override persisted context', async () => {
    localStorage.setItem('gradtutor_user', 'user-a')
    localStorage.setItem(
      persistedKey('user-a'),
      JSON.stringify({ selectedKbId: 'kb-1', selectedDocId: 'doc-1' })
    )

    const store = useAppContextStore()
    store.hydrate()
    store.kbs = [
      { id: 'kb-1', name: 'KB 1' },
      { id: 'kb-2', name: 'KB 2' },
    ]
    store.kbsUserId = 'user-a'

    await store.applyRouteContext({
      kb_id: 'kb-2',
      doc_id: 'doc-2',
      focus: 'graph',
      difficulty: 'hard',
      keypoint_text: 'adjacency',
    })

    expect(store.selectedKbId).toBe('kb-2')
    expect(store.selectedDocId).toBe('doc-2')
    expect(store.routeContext).toEqual({
      focus: 'graph',
      difficulty: 'hard',
      keypointText: 'adjacency',
    })

    const persisted = JSON.parse(localStorage.getItem(persistedKey('user-a')) || '{}')
    expect(persisted).toMatchObject({ selectedKbId: 'kb-2', selectedDocId: 'doc-2' })
  })

  it('deduplicates in-flight kb requests', async () => {
    localStorage.setItem('gradtutor_user', 'user-a')

    let resolveRequest
    apiGet.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve
        })
    )

    const store = useAppContextStore()
    store.hydrate()

    const req1 = store.loadKbs(true)
    const req2 = store.loadKbs(true)

    expect(apiGet).toHaveBeenCalledTimes(1)

    resolveRequest([{ id: 'kb-1', name: 'KB 1' }])
    const [result1, result2] = await Promise.all([req1, req2])
    await flushPromises()

    expect(result1).toEqual(result2)
    expect(store.kbs).toHaveLength(1)
    expect(store.selectedKbId).toBe('kb-1')
  })

  it('logout clears app context keys', () => {
    localStorage.setItem('gradtutor_user_id', 'u1')
    localStorage.setItem('gradtutor_username', 'u1')
    localStorage.setItem('gradtutor_name', 'U1')
    localStorage.setItem('gradtutor_user', 'u1')
    localStorage.setItem('gradtutor_access_token', 'token')
    localStorage.setItem(persistedKey('u1'), JSON.stringify({ selectedKbId: 'kb-1', selectedDocId: '' }))

    try {
      logout()
    } catch {
      // jsdom may throw on navigation
    }

    expect(localStorage.getItem('gradtutor_user_id')).toBeNull()
    expect(localStorage.getItem('gradtutor_username')).toBeNull()
    expect(localStorage.getItem('gradtutor_name')).toBeNull()
    expect(localStorage.getItem('gradtutor_user')).toBeNull()
    expect(localStorage.getItem('gradtutor_access_token')).toBeNull()

    const keys = Object.keys(localStorage)
    expect(keys.some((key) => key.startsWith(APP_CONTEXT_KEY_PREFIX))).toBe(false)
  })
})
