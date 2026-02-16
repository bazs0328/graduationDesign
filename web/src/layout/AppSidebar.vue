<template>
  <aside class="w-64 bg-card border-r border-border flex flex-col h-screen transition-all duration-300" :class="{ 'w-20': collapsed }">
    <div class="p-6 flex items-center gap-3 border-b border-border">
      <div class="w-8 h-8 bg-primary rounded-lg flex items-center justify-center text-primary-foreground font-bold">G</div>
      <h1 v-if="!collapsed" class="text-xl font-bold tracking-tight">GradTutor</h1>
    </div>

    <nav class="flex-1 p-4 space-y-2 overflow-y-auto">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 hover:bg-primary/10 hover:text-primary group"
        :class="{ 'bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground shadow-md shadow-primary/20': $route.path === item.path }"
      >
        <component :is="item.icon" class="w-5 h-5" />
        <span v-if="!collapsed" class="font-semibold">{{ item.name }}</span>
        <div v-if="collapsed" class="absolute left-16 bg-popover text-popover-foreground px-2 py-1 rounded shadow-md opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50 whitespace-nowrap">
          {{ item.name }}
        </div>
      </router-link>
    </nav>

    <div class="p-4 border-t border-border space-y-4">
      <div v-if="!collapsed" class="space-y-2">
        <p class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">当前用户</p>
        <p class="text-sm font-medium truncate" :title="displayName">{{ displayName }}</p>
        <button
          type="button"
          @click="handleLogout"
          class="w-full py-2 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
        >
          退出登录
        </button>
      </div>
      <button
        @click="collapsed = !collapsed"
        class="w-full flex items-center justify-center p-2 rounded-md hover:bg-accent transition-colors"
      >
        <component :is="collapsed ? 'ChevronRight' : 'ChevronLeft'" class="w-5 h-5" />
      </button>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed } from 'vue'
import {
  Home,
  Upload,
  FileText,
  MessageSquare,
  PenTool,
  BarChart2,
  ChevronLeft,
  ChevronRight
} from 'lucide-vue-next'
import { getCurrentUser, logout } from '../api'

const collapsed = ref(false)

const displayName = computed(() => {
  const user = getCurrentUser()
  return user ? (user.name || user.username) : '—'
})

function handleLogout() {
  logout()
}

const navItems = [
  { name: '首页', path: '/', icon: Home },
  { name: '上传', path: '/upload', icon: Upload },
  { name: '摘要', path: '/summary', icon: FileText },
  { name: '问答', path: '/qa', icon: MessageSquare },
  { name: '测验', path: '/quiz', icon: PenTool },
  { name: '进度', path: '/progress', icon: BarChart2 }
]
</script>
