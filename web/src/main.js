import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { enableGlobalErrorToast } from './api'
import { useAppContextStore } from './stores/appContext'
import 'katex/dist/katex.min.css'
import './styles/index.css'

enableGlobalErrorToast()

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
useAppContextStore(pinia).hydrate()
app.use(router)
app.mount('#app')
