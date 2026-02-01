import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue')
  },
  {
    path: '/upload',
    name: 'Upload',
    component: () => import('../views/Upload.vue')
  },
  {
    path: '/summary',
    name: 'Summary',
    component: () => import('../views/Summary.vue')
  },
  {
    path: '/qa',
    name: 'QA',
    component: () => import('../views/QA.vue')
  },
  {
    path: '/quiz',
    name: 'Quiz',
    component: () => import('../views/Quiz.vue')
  },
  {
    path: '/progress',
    name: 'Progress',
    component: () => import('../views/Progress.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
