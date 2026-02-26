<template>
  <div
    v-if="mobileOpen"
    class="fixed inset-0 z-40 bg-black/35 backdrop-blur-[1px] lg:hidden"
    @click="closeMobileDrawer"
  ></div>
  <aside
    class="bg-card border-r border-border flex flex-col h-screen transition-all duration-300 fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] shadow-2xl lg:static lg:translate-x-0 lg:w-64 lg:max-w-none lg:shadow-none"
    :class="[
      mobileOpen ? 'translate-x-0' : '-translate-x-full',
      collapsed ? 'lg:w-20' : 'lg:w-64'
    ]"
  >
    <div class="p-4 lg:p-6 flex items-center gap-3 border-b border-border justify-between">
      <div class="flex items-center gap-3 min-w-0">
        <div class="w-8 h-8 bg-primary rounded-lg flex items-center justify-center text-primary-foreground font-bold shrink-0">G</div>
        <h1 v-if="showExpandedLabels" class="text-xl font-bold tracking-tight truncate">GradTutor</h1>
      </div>
      <button
        type="button"
        class="lg:hidden p-2 rounded-md hover:bg-accent transition-colors"
        @click="closeMobileDrawer"
        aria-label="关闭导航菜单"
      >
        <X class="w-5 h-5" />
      </button>
    </div>

    <nav class="flex-1 p-3 lg:p-4 space-y-2 overflow-y-auto">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="relative flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 hover:bg-primary/10 hover:text-primary group"
        :class="{ 'bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground shadow-md shadow-primary/20': $route.path === item.path }"
        @click="closeMobileDrawer"
      >
        <component :is="item.icon" class="w-5 h-5 shrink-0" />
        <span v-if="showExpandedLabels" class="font-semibold truncate">{{ item.name }}</span>
        <div
          v-if="collapsed && !mobileOpen"
          class="absolute left-16 bg-popover text-popover-foreground px-2 py-1 rounded shadow-md opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50 whitespace-nowrap"
        >
          {{ item.name }}
        </div>
      </router-link>
    </nav>

    <div class="p-3 lg:p-4 border-t border-border space-y-3 lg:space-y-4">
      <div v-if="showExpandedLabels" class="space-y-2">
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
        class="hidden lg:flex w-full items-center justify-center p-2 rounded-md hover:bg-accent transition-colors"
        @click="collapsed = !collapsed"
      >
        <component :is="collapsed ? 'ChevronRight' : 'ChevronLeft'" class="w-5 h-5" />
      </button>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  Home,
  Upload,
  FileText,
  MessageSquare,
  PenTool,
  BarChart2,
  SlidersHorizontal,
  ChevronLeft,
  ChevronRight,
  X
} from 'lucide-vue-next'
import { getCurrentUser, logout } from '../api'

const route = useRoute()
const collapsed = ref(false)
const mobileOpen = ref(false)

const displayName = computed(() => {
  const user = getCurrentUser()
  return user ? (user.name || user.username) : '—'
})
const showExpandedLabels = computed(() => mobileOpen.value || !collapsed.value)

function handleLogout() {
  logout()
}

function isDesktopViewport() {
  if (typeof window === 'undefined') return true
  if (typeof window.matchMedia !== 'function') return true
  return window.matchMedia('(min-width: 1024px)').matches
}

function closeMobileDrawer() {
  if (!isDesktopViewport()) {
    mobileOpen.value = false
  }
}

function handleSidebarToggleEvent() {
  if (isDesktopViewport()) return
  mobileOpen.value = !mobileOpen.value
}

function handleSidebarCloseEvent() {
  mobileOpen.value = false
}

const navItems = [
  { name: '首页', path: '/', icon: Home },
  { name: '上传', path: '/upload', icon: Upload },
  { name: '摘要', path: '/summary', icon: FileText },
  { name: '问答', path: '/qa', icon: MessageSquare },
  { name: '测验', path: '/quiz', icon: PenTool },
  { name: '进度', path: '/progress', icon: BarChart2 },
  { name: '设置', path: '/settings', icon: SlidersHorizontal }
]

watch(() => route.fullPath, () => {
  closeMobileDrawer()
})

onMounted(() => {
  if (typeof window === 'undefined') return
  window.addEventListener('gradtutor:toggle-sidebar', handleSidebarToggleEvent)
  window.addEventListener('gradtutor:close-sidebar', handleSidebarCloseEvent)
})

onUnmounted(() => {
  if (typeof window === 'undefined') return
  window.removeEventListener('gradtutor:toggle-sidebar', handleSidebarToggleEvent)
  window.removeEventListener('gradtutor:close-sidebar', handleSidebarCloseEvent)
})
</script>
