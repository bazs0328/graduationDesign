import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { enableGlobalErrorToast } from './api'
import { useAppContextStore } from './stores/appContext'
import 'katex/dist/katex.min.css'
import './styles/index.css'

const THEME_STORAGE_KEY = 'gradtutor_theme'

function resolveInitialTheme() {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    // ignore localStorage access errors
  }
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return 'light'
}

function applyTheme(theme) {
  const root = document.documentElement
  const resolved = theme === 'dark' ? 'dark' : 'light'
  root.classList.toggle('dark', resolved === 'dark')
  root.classList.toggle('light', resolved === 'light')
}

enableGlobalErrorToast()
applyTheme(resolveInitialTheme())

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
useAppContextStore(pinia).hydrate()
app.use(router)
app.mount('#app')
