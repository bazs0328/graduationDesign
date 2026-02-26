import { describe, it, expect, beforeEach, vi } from 'vitest'

async function loadThemeModule() {
  vi.resetModules()
  return import('../../src/composables/useTheme.js')
}

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.className = ''
  })

  it('initializes from localStorage and applies class to document', async () => {
    localStorage.setItem('gradtutor_theme', 'dark')
    const theme = await loadThemeModule()

    const initial = theme.initializeTheme()

    expect(initial).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(document.documentElement.classList.contains('light')).toBe(false)
  })

  it('persists theme changes and toggles correctly', async () => {
    const theme = await loadThemeModule()

    theme.setTheme('dark')
    expect(localStorage.getItem('gradtutor_theme')).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    theme.toggleTheme()
    expect(localStorage.getItem('gradtutor_theme')).toBe('light')
    expect(document.documentElement.classList.contains('light')).toBe(true)
  })
})

