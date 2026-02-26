export const AUTH_SESSION_KEYS = {
  userId: 'gradtutor_user_id',
  username: 'gradtutor_username',
  name: 'gradtutor_name',
  user: 'gradtutor_user',
  accessToken: 'gradtutor_access_token',
}

const APP_CONTEXT_KEY_PREFIX = 'gradtutor_app_ctx_v1:'

function safeLocalStorage() {
  if (typeof localStorage === 'undefined') return null
  return localStorage
}

export function getAccessToken() {
  const storage = safeLocalStorage()
  return storage?.getItem(AUTH_SESSION_KEYS.accessToken) || ''
}

export function hasAccessToken() {
  return Boolean(getAccessToken())
}

export function getCurrentUserFromSession() {
  const storage = safeLocalStorage()
  if (!storage) return null
  const userId = storage.getItem(AUTH_SESSION_KEYS.userId)
  const username = storage.getItem(AUTH_SESSION_KEYS.username)
  const name = storage.getItem(AUTH_SESSION_KEYS.name)
  const token = storage.getItem(AUTH_SESSION_KEYS.accessToken)
  if (!userId) return null
  return {
    user_id: userId,
    username: username || userId,
    name: name || username || userId,
    access_token: token || '',
  }
}

export function setAuthSessionFromResponse(res) {
  const storage = safeLocalStorage()
  if (!storage || !res?.user_id) return
  storage.setItem(AUTH_SESSION_KEYS.userId, res.user_id)
  storage.setItem(AUTH_SESSION_KEYS.username, res.username || res.user_id)
  storage.setItem(AUTH_SESSION_KEYS.name, res.name || '')
  storage.setItem(AUTH_SESSION_KEYS.user, res.user_id)
  if (res.access_token) {
    storage.setItem(AUTH_SESSION_KEYS.accessToken, res.access_token)
  } else {
    storage.removeItem(AUTH_SESSION_KEYS.accessToken)
  }
}

export function clearAppContextStorage() {
  const storage = safeLocalStorage()
  if (!storage) return
  const keys = []
  for (let idx = 0; idx < storage.length; idx += 1) {
    const key = storage.key(idx)
    if (key && key.startsWith(APP_CONTEXT_KEY_PREFIX)) keys.push(key)
  }
  keys.forEach((key) => storage.removeItem(key))
}

export function clearAuthSession() {
  const storage = safeLocalStorage()
  if (!storage) return
  clearAppContextStorage()
  storage.removeItem(AUTH_SESSION_KEYS.userId)
  storage.removeItem(AUTH_SESSION_KEYS.username)
  storage.removeItem(AUTH_SESSION_KEYS.name)
  storage.removeItem(AUTH_SESSION_KEYS.user)
  storage.removeItem(AUTH_SESSION_KEYS.accessToken)
}

export function useAuthSession() {
  return {
    getAccessToken,
    hasAccessToken,
    getCurrentUser: getCurrentUserFromSession,
    setAuthSessionFromResponse,
    clearAuthSession,
    clearAppContextStorage,
  }
}
