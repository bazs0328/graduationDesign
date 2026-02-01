import { createRouter, createWebHistory } from 'vue-router'

const routes = [
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
    meta: { title: '问答' },
    component: () => import('../views/QA.vue')
  },
  {
    path: '/quiz',
    name: 'Quiz',
    meta: { title: '测验' },
    component: () => import('../views/Quiz.vue')
  },
  {
    path: '/progress',
    name: 'Progress',
    meta: { title: '进度' },
    component: () => import('../views/Progress.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
