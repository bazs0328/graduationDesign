import { computed, ref } from 'vue'

export const THEME_STORAGE_KEY = 'gradtutor_theme'

const themeState = ref('light')
let initialized = false

function normalizeTheme(value) {
  return value === 'dark' ? 'dark' : 'light'
}

export function readThemeFromDom() {
  if (typeof document === 'undefined') return 'light'
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

export function resolveStoredTheme() {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    // ignore localStorage access errors
  }
  return null
}

export function resolveInitialTheme() {
  const stored = resolveStoredTheme()
  if (stored) return stored
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return 'light'
}

export function applyTheme(theme) {
  if (typeof document === 'undefined') return
  const resolved = normalizeTheme(theme)
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
  root.classList.toggle('light', resolved === 'light')
  themeState.value = resolved
}

export function setTheme(theme, options = {}) {
  const { persist = true } = options
  const resolved = normalizeTheme(theme)
  applyTheme(resolved)
  if (persist) {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, resolved)
    } catch {
      // ignore localStorage access errors
    }
  }
  return resolved
}

export function toggleTheme() {
  return setTheme(themeState.value === 'dark' ? 'light' : 'dark')
}

export function initializeTheme() {
  if (initialized) return themeState.value
  const initial = resolveInitialTheme()
  applyTheme(initial)
  initialized = true
  return initial
}

export function useTheme() {
  if (!initialized && typeof document !== 'undefined') {
    themeState.value = readThemeFromDom()
  }
  return {
    theme: computed(() => themeState.value),
    isDark: computed(() => themeState.value === 'dark'),
    setTheme,
    toggleTheme,
    applyTheme,
    initializeTheme,
  }
}
