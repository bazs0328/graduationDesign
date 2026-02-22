import { useToast } from './composables/useToast'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

let globalErrorToast = false

export function enableGlobalErrorToast() {
  globalErrorToast = true
}

function buildAuthHeaders(path, headersLike) {
  const isAuth = path.includes('/api/auth')
  const headers = new Headers(headersLike || undefined)
  if (!isAuth) {
    const token = localStorage.getItem('gradtutor_access_token')
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
  }
  return { headers, isAuth }
}

async function parseErrorResponse(res) {
  const text = await res.text()
  throw createErrorFromResponseText(text, res.status)
}

function createErrorFromResponseText(text, status) {
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
        return new Error(message)
      }
      if (typeof data.detail === 'string') {
        return new Error(data.detail)
      }
      return new Error(JSON.stringify(data.detail))
    }
  } catch {
    // fall through to raw text message
  }
  return new Error(text || `Request failed: ${status}`)
}

function maybeShowGlobalErrorToast(err) {
  if (globalErrorToast) {
    const { showToast } = useToast()
    showToast(err.message || '请求失败', 'error')
  }
}

async function request(path, options = {}) {
  const fullUrl = `${API_BASE}${path}`
  const { headers, isAuth } = buildAuthHeaders(path, options.headers)
  let abortId
  let signal = options.signal
  if (isAuth && !signal) {
    const controller = new AbortController()
    signal = controller.signal
    abortId = setTimeout(() => controller.abort(), 15000)
  }
  try {
    const res = await fetch(fullUrl, { ...options, headers, signal })
    if (abortId) clearTimeout(abortId)
    if (!res.ok) {
      await parseErrorResponse(res)
    }
    return res.json()
  } catch (err) {
    if (abortId) clearTimeout(abortId)
    maybeShowGlobalErrorToast(err)
    throw err
  }
}

function parseSseBlocks(buffer) {
  const normalized = buffer.replace(/\r\n/g, '\n')
  const blocks = normalized.split('\n\n')
  return {
    completeBlocks: blocks.slice(0, -1),
    remainder: blocks.at(-1) ?? ''
  }
}

function parseSseEventBlock(block) {
  let eventName = 'message'
  const dataParts = []
  for (const line of block.split('\n')) {
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim() || 'message'
      continue
    }
    if (line.startsWith('data:')) {
      dataParts.push(line.slice(5).trimStart())
    }
  }
  if (!dataParts.length) return null
  const rawData = dataParts.join('\n')
  let data = rawData
  try {
    data = JSON.parse(rawData)
  } catch {
    // keep raw string for non-JSON events
  }
  return { event: eventName, data }
}

function dispatchSseEvent(parsed, handlers = {}) {
  if (!parsed) return
  const { event, data } = parsed
  if (event === 'status' && typeof handlers.onStatus === 'function') handlers.onStatus(data)
  if (event === 'chunk' && typeof handlers.onChunk === 'function') handlers.onChunk(data)
  if (event === 'sources' && typeof handlers.onSources === 'function') handlers.onSources(data)
  if (event === 'done' && typeof handlers.onDone === 'function') handlers.onDone(data)
  if (event === 'error' && typeof handlers.onError === 'function') handlers.onError(data)
  if (typeof handlers.onEvent === 'function') handlers.onEvent(event, data)
}

async function consumeSseResponse(res, handlers = {}) {
  if (!res.body) {
    throw new Error('SSE stream body is empty')
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const { completeBlocks, remainder } = parseSseBlocks(buffer)
    buffer = remainder
    for (const block of completeBlocks) {
      const parsed = parseSseEventBlock(block)
      dispatchSseEvent(parsed, handlers)
    }
  }

  buffer += decoder.decode()
  const tailBlock = parseSseEventBlock(buffer)
  dispatchSseEvent(tailBlock, handlers)
}

export async function apiSsePost(path, body, handlers = {}, options = {}) {
  const fullUrl = `${API_BASE}${path}`
  const { headers } = buildAuthHeaders(path, options.headers)
  headers.set('Accept', 'text/event-stream')
  headers.set('Content-Type', 'application/json')

  try {
    const res = await fetch(fullUrl, {
      method: 'POST',
      ...options,
      headers,
      body: JSON.stringify(body)
    })
    if (!res.ok) {
      await parseErrorResponse(res)
    }
    await consumeSseResponse(res, handlers)
  } catch (err) {
    maybeShowGlobalErrorToast(err)
    throw err
  }
}

export async function apiSseGet(path, handlers = {}, options = {}) {
  const fullUrl = `${API_BASE}${path}`
  const { headers } = buildAuthHeaders(path, options.headers)
  headers.set('Accept', 'text/event-stream')
  try {
    const res = await fetch(fullUrl, {
      method: 'GET',
      ...options,
      headers
    })
    if (!res.ok) {
      await parseErrorResponse(res)
    }
    await consumeSseResponse(res, handlers)
  } catch (err) {
    maybeShowGlobalErrorToast(err)
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
  const token = localStorage.getItem('gradtutor_access_token')
  if (!userId) return null
  return { user_id: userId, username: username || userId, name: name || username || userId, access_token: token }
}

export function logout() {
  const appCtxKeys = []
  for (let idx = 0; idx < localStorage.length; idx += 1) {
    const key = localStorage.key(idx)
    if (key && key.startsWith('gradtutor_app_ctx_v1:')) {
      appCtxKeys.push(key)
    }
  }
  appCtxKeys.forEach((key) => localStorage.removeItem(key))
  localStorage.removeItem('gradtutor_user_id')
  localStorage.removeItem('gradtutor_username')
  localStorage.removeItem('gradtutor_name')
  localStorage.removeItem('gradtutor_user')
  localStorage.removeItem('gradtutor_access_token')
  const userAgent = typeof navigator !== 'undefined' ? navigator.userAgent || '' : ''
  if (!/jsdom/i.test(userAgent)) {
    window.location.href = '/login'
  }
}

export async function apiPost(path, body, isForm = false) {
  const options = {
    method: 'POST',
    headers: isForm ? undefined : { 'Content-Type': 'application/json' },
    body: isForm ? body : JSON.stringify(body)
  }
  return request(path, options)
}

export async function apiUploadWithProgress(path, formData, options = {}) {
  const fullUrl = `${API_BASE}${path}`
  const { headers } = buildAuthHeaders(path, options.headers)
  const { onProgress, signal } = options

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    let aborted = false

    const cleanupAbortListener = () => {
      if (signal) {
        signal.removeEventListener('abort', handleAbort)
      }
    }

    const rejectWithToast = (err) => {
      maybeShowGlobalErrorToast(err)
      reject(err)
    }

    function handleAbort() {
      aborted = true
      try {
        xhr.abort()
      } catch {
        // no-op
      }
    }

    if (signal?.aborted) {
      const abortErr = new DOMException('The operation was aborted.', 'AbortError')
      rejectWithToast(abortErr)
      return
    }

    xhr.open('POST', fullUrl)

    headers.forEach((value, key) => {
      // Let the browser set multipart boundary automatically.
      if (key.toLowerCase() !== 'content-type') {
        xhr.setRequestHeader(key, value)
      }
    })

    if (typeof onProgress === 'function' && xhr.upload) {
      xhr.upload.onprogress = (event) => {
        const total = event.lengthComputable ? event.total : 0
        const loaded = event.loaded || 0
        const percent = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0
        onProgress({ percent, loaded, total, lengthComputable: !!event.lengthComputable })
      }
    }

    xhr.onload = () => {
      cleanupAbortListener()
      const responseText = xhr.responseText || ''
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(responseText ? JSON.parse(responseText) : null)
        } catch {
          rejectWithToast(new Error('Invalid JSON response'))
        }
        return
      }
      rejectWithToast(createErrorFromResponseText(responseText, xhr.status))
    }

    xhr.onerror = () => {
      cleanupAbortListener()
      rejectWithToast(new Error('Failed to fetch'))
    }

    xhr.onabort = () => {
      cleanupAbortListener()
      const abortErr = new DOMException('The operation was aborted.', 'AbortError')
      if (aborted) {
        rejectWithToast(abortErr)
      } else {
        rejectWithToast(abortErr)
      }
    }

    if (signal) {
      signal.addEventListener('abort', handleAbort, { once: true })
    }

    try {
      xhr.send(formData)
    } catch (err) {
      cleanupAbortListener()
      rejectWithToast(err)
    }
  })
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
