import { beforeEach, describe, expect, it } from 'vitest'
import {
  AUTH_SESSION_KEYS,
  clearAppContextStorage,
  clearAuthSession,
  getCurrentUserFromSession,
  hasAccessToken,
  setAuthSessionFromResponse,
} from '../../src/composables/useAuthSession'

describe('useAuthSession', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('writes and reads auth session using legacy-compatible keys', () => {
    setAuthSessionFromResponse({
      user_id: 'u-1',
      username: 'alice',
      name: 'Alice',
      access_token: 'token-123',
    })

    expect(localStorage.getItem(AUTH_SESSION_KEYS.userId)).toBe('u-1')
    expect(localStorage.getItem(AUTH_SESSION_KEYS.user)).toBe('u-1')
    expect(localStorage.getItem(AUTH_SESSION_KEYS.username)).toBe('alice')
    expect(localStorage.getItem(AUTH_SESSION_KEYS.name)).toBe('Alice')
    expect(localStorage.getItem(AUTH_SESSION_KEYS.accessToken)).toBe('token-123')
    expect(hasAccessToken()).toBe(true)
    expect(getCurrentUserFromSession()).toEqual({
      user_id: 'u-1',
      username: 'alice',
      name: 'Alice',
      access_token: 'token-123',
    })
  })

  it('clears app context storage prefix and auth keys on logout', () => {
    localStorage.setItem('gradtutor_app_ctx_v1:u-1', '{"selectedKbId":"kb1"}')
    localStorage.setItem('gradtutor_app_ctx_v1:u-2', '{"selectedKbId":"kb2"}')
    localStorage.setItem('unrelated_key', 'keep')
    setAuthSessionFromResponse({
      user_id: 'u-1',
      username: 'alice',
      name: 'Alice',
      access_token: 'token-123',
    })

    clearAppContextStorage()
    expect(localStorage.getItem('gradtutor_app_ctx_v1:u-1')).toBeNull()
    expect(localStorage.getItem('gradtutor_app_ctx_v1:u-2')).toBeNull()
    expect(localStorage.getItem('unrelated_key')).toBe('keep')

    clearAuthSession()
    expect(localStorage.getItem(AUTH_SESSION_KEYS.userId)).toBeNull()
    expect(localStorage.getItem(AUTH_SESSION_KEYS.accessToken)).toBeNull()
    expect(localStorage.getItem('unrelated_key')).toBe('keep')
  })
})

