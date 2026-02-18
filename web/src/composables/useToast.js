import { reactive } from 'vue'

let nextId = 0

const DEFAULT_DURATION = {
  success: 3000,
  info: 3000,
  warning: 3000,
  error: 5000,
}

const toasts = reactive([])

function showToast(message, type = 'info', duration) {
  const id = ++nextId
  const ms = duration ?? DEFAULT_DURATION[type] ?? 3000

  toasts.push({ id, message, type, duration: ms })

  if (ms > 0) {
    setTimeout(() => removeToast(id), ms)
  }

  return id
}

function removeToast(id) {
  const idx = toasts.findIndex((t) => t.id === id)
  if (idx !== -1) toasts.splice(idx, 1)
}

export function useToast() {
  return { toasts, showToast, removeToast }
}
