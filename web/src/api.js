import { useToast } from './composables/useToast'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

let globalErrorToast = false

export function enableGlobalErrorToast() {
  globalErrorToast = true
}

async function request(path, options = {}) {
  const fullUrl = `${API_BASE}${path}`
  const isAuth = path.includes('/api/auth')
  let abortId
  let signal = options.signal
  if (isAuth && !signal) {
    const controller = new AbortController()
    signal = controller.signal
    abortId = setTimeout(() => controller.abort(), 15000)
  }
  try {
    const res = await fetch(fullUrl, { ...options, signal })
    if (abortId) clearTimeout(abortId)
    if (!res.ok) {
      const text = await res.text()
      try {
        const data = JSON.parse(text)
        if (data && data.detail) {
          if (Array.isArray(data.detail)) {
            const message = data.detail
              .map((item) => {
                if (!item || typeof item !== 'object') {
                  return String(item)
                }
                const loc = Array.isArray(item.loc) ? item.loc.join('.') : ''
                const msg = item.msg || item.message || JSON.stringify(item)
                return loc ? `${loc}: ${msg}` : msg
              })
              .join('; ')
            throw new Error(message)
          }
          if (typeof data.detail === 'string') {
            throw new Error(data.detail)
          }
          throw new Error(JSON.stringify(data.detail))
        }
      } catch (err) {
        if (err instanceof Error && err.message) {
          throw err
        }
      }
      throw new Error(text || `Request failed: ${res.status}`)
    }
    return res.json()
  } catch (err) {
    if (abortId) clearTimeout(abortId)
    if (globalErrorToast) {
      const { showToast } = useToast()
      showToast(err.message || '请求失败', 'error')
    }
    throw err
  }
}

export async function apiGet(path) {
  return request(path)
}

export async function authRegister(username, password, name = null) {
  return apiPost('/api/auth/register', { username, password, name })
}

export async function authLogin(username, password) {
  return apiPost('/api/auth/login', { username, password })
}

export function getCurrentUser() {
  const userId = localStorage.getItem('gradtutor_user_id')
  const username = localStorage.getItem('gradtutor_username')
  const name = localStorage.getItem('gradtutor_name')
  if (!userId) return null
  return { user_id: userId, username: username || userId, name: name || username || userId }
}

export function logout() {
  localStorage.removeItem('gradtutor_user_id')
  localStorage.removeItem('gradtutor_username')
  localStorage.removeItem('gradtutor_name')
  localStorage.removeItem('gradtutor_user')
  window.location.href = '/login'
}

export async function apiPost(path, body, isForm = false) {
  const options = {
    method: 'POST',
    headers: isForm ? undefined : { 'Content-Type': 'application/json' },
    body: isForm ? body : JSON.stringify(body)
  }
  return request(path, options)
}

export async function apiPatch(path, body) {
  return request(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
}

export async function apiDelete(path) {
  return request(path, { method: 'DELETE' })
}

export async function getProfile(userId) {
  const query = userId ? `?user_id=${encodeURIComponent(userId)}` : ''
  return apiGet(`/api/profile${query}`)
}

export async function getDifficultyPlan(userId) {
  const query = userId ? `?user_id=${encodeURIComponent(userId)}` : ''
  return apiGet(`/api/profile/difficulty-plan${query}`)
}

export async function buildLearningPath(userId, kbId, force = false) {
  const params = new URLSearchParams({ kb_id: kbId, force: String(force) })
  if (userId) params.set('user_id', userId)
  return apiPost(`/api/learning-path/build?${params}`)
}
