import { createRouter, createWebHistory } from 'vue-router'
import { authMe } from '../api'
import { getAccessToken, hasAccessToken, setAuthSessionFromResponse } from '../composables/useAuthSession'

export const routes = [
  {
    path: '/login',
    name: 'Login',
    meta: { title: '登录' },
    component: () => import('../views/Login.vue')
  },
  {
    path: '/',
    name: 'Home',
    meta: { title: '首页' },
    component: () => import('../views/Home.vue')
  },
  {
    path: '/upload',
    name: 'Upload',
    meta: { title: '上传' },
    component: () => import('../views/Upload.vue')
  },
  {
    path: '/summary',
    name: 'Summary',
    meta: { title: '摘要' },
    component: () => import('../views/Summary.vue')
  },
  {
    path: '/qa',
    name: 'QA',
    meta: { title: '问答', showHeaderContextBar: false },
    component: () => import('../views/QA.vue')
  },
  {
    path: '/quiz',
    name: 'Quiz',
    meta: { title: '测验', showHeaderContextBar: false },
    component: () => import('../views/Quiz.vue')
  },
  {
    path: '/progress',
    name: 'Progress',
    meta: { title: '进度' },
    component: () => import('../views/Progress.vue')
  },
  {
    path: '/settings',
    name: 'Settings',
    meta: { title: '设置中心' },
    component: () => import('../views/Settings.vue')
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    meta: { title: '页面未找到' },
    component: () => import('../views/NotFound.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

let validatedToken = ''
let pendingValidation = null

async function ensureAuthenticatedSession() {
  const token = getAccessToken()
  if (!token) {
    validatedToken = ''
    return false
  }
  if (validatedToken === token) return true
  if (pendingValidation?.token === token) {
    return pendingValidation.promise
  }

  const promise = authMe()
    .then((payload) => {
      if (payload?.user_id) {
        setAuthSessionFromResponse(payload)
      }
      validatedToken = getAccessToken() || token
      return true
    })
    .catch(() => {
      validatedToken = ''
      return false
    })
    .finally(() => {
      if (pendingValidation?.token === token) {
        pendingValidation = null
      }
    })

  pendingValidation = { token, promise }
  return promise
}

router.afterEach((to) => {
  const title = to.meta?.title
  document.title = title ? `${title} - StudyCompass` : 'StudyCompass - 智能学习助手'
})

router.beforeEach(async (to, from, next) => {
  const isLoggedIn = hasAccessToken()
  if (!isLoggedIn && to.path !== '/login') {
    next('/login')
    return
  }
  if (!isLoggedIn) {
    next()
    return
  }

  const sessionOk = await ensureAuthenticatedSession()
  if (!sessionOk) {
    next('/login')
    return
  }

  if (to.path === '/login') {
    next('/')
    return
  }

  next()
})

export default router
