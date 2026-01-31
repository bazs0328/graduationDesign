const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options)
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
}

export async function apiGet(path) {
  return request(path)
}

export async function apiPost(path, body, isForm = false) {
  const options = {
    method: 'POST',
    headers: isForm ? undefined : { 'Content-Type': 'application/json' },
    body: isForm ? body : JSON.stringify(body)
  }
  return request(path, options)
}
