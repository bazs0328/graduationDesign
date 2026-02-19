import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { enableGlobalErrorToast } from './api'
import './styles/index.css'

enableGlobalErrorToast()

const app = createApp(App)
app.use(router)
app.mount('#app')
