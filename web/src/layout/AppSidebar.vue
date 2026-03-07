<template>
  <div
    v-if="mobileOpen"
    class="fixed inset-0 z-40 bg-black/35 backdrop-blur-[1px] lg:hidden"
    @click="closeMobileDrawer"
  ></div>
  <aside
    :aria-hidden="sidebarInteractive ? 'false' : 'true'"
    :inert="sidebarInteractive ? null : ''"
    class="flex flex-col h-screen transition-all duration-300 fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] shadow-2xl lg:static lg:translate-x-0 lg:w-64 lg:max-w-none lg:shadow-none bg-slate-50/92 dark:bg-slate-900/90 border-r border-border/80 backdrop-blur-xl"
    :class="[
      mobileOpen ? 'translate-x-0' : '-translate-x-full',
      collapsed ? 'lg:hidden' : 'lg:w-64'
    ]"
  >
    <div class="p-4 lg:p-5 flex items-center gap-3 border-b border-border/70 justify-between">
      <div class="flex items-center gap-3 min-w-0">
        <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center text-white font-bold shrink-0 shadow-lg shadow-blue-500/20">G</div>
        <div v-if="showExpandedLabels" class="min-w-0">
          <p class="text-[10px] font-bold uppercase tracking-[0.26em] text-slate-500 dark:text-slate-400">Workspace</p>
          <h1 class="text-lg font-bold tracking-tight truncate">GradTutor</h1>
        </div>
      </div>
      <button
        ref="mobileCloseButtonRef"
        type="button"
        class="lg:hidden p-2 rounded-md hover:bg-accent transition-colors"
        @click="closeMobileDrawer"
        aria-label="关闭导航菜单"
      >
        <X class="w-5 h-5" />
      </button>
    </div>

    <nav class="flex-1 p-3 lg:p-4 space-y-2 overflow-y-auto">
      <p
        v-if="showExpandedLabels"
        class="px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.24em] text-muted-foreground"
      >
        主流程
      </p>
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="relative flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200 hover:bg-white/80 hover:text-primary dark:hover:bg-slate-800/90 group"
        :class="{ 'bg-white text-slate-950 hover:bg-white shadow-[0_16px_28px_-22px_rgba(15,23,42,0.35)] dark:bg-slate-800 dark:text-slate-100': $route.path === item.path }"
        @click="closeMobileDrawer"
      >
        <component :is="item.icon" class="w-5 h-5 shrink-0" :class="$route.path === item.path ? 'text-primary' : 'text-muted-foreground'" />
        <span v-if="showExpandedLabels" class="font-semibold truncate">{{ item.name }}</span>
      </router-link>
    </nav>

    <div class="p-3 lg:p-4 border-t border-border/70 space-y-3 lg:space-y-4">
      <div v-if="showExpandedLabels" class="workspace-card-soft p-3 space-y-2">
        <p class="text-[10px] font-bold uppercase tracking-[0.24em] text-muted-foreground">当前用户</p>
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
        class="hidden lg:flex w-full items-center justify-center p-2 rounded-xl hover:bg-white/80 dark:hover:bg-slate-800 transition-colors"
        @click="collapsed = !collapsed"
        aria-label="隐藏导航栏"
        title="隐藏导航栏"
      >
        <ChevronLeft class="w-5 h-5" />
      </button>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
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
  X
} from 'lucide-vue-next'
import { getCurrentUser, logout } from '../api'

const route = useRoute()
const collapsed = ref(false)
const mobileOpen = ref(false)
const isDesktop = ref(true)
const mobileCloseButtonRef = ref(null)

const displayName = computed(() => {
  const user = getCurrentUser()
  return user ? (user.name || user.username) : '—'
})
const showExpandedLabels = computed(() => !collapsed.value || mobileOpen.value)
const sidebarInteractive = computed(() => (isDesktop.value && !collapsed.value) || mobileOpen.value)

let lastFocusedElement = null

function handleLogout() {
  logout()
}

function isDesktopViewport() {
  if (typeof window === 'undefined') return true
  if (typeof window.matchMedia !== 'function') return true
  return window.matchMedia('(min-width: 1024px)').matches
}

function syncViewportState() {
  isDesktop.value = isDesktopViewport()
}

function setBodyScrollLock(locked) {
  if (typeof document === 'undefined') return
  document.body.style.overflow = locked ? 'hidden' : ''
}

function restoreFocusAfterClose() {
  if (!(lastFocusedElement instanceof HTMLElement)) {
    lastFocusedElement = null
    return
  }
  try {
    lastFocusedElement.focus()
  } catch {
    // ignore stale focus targets
  }
  lastFocusedElement = null
}

function closeMobileDrawer() {
  if (!isDesktop.value) {
    mobileOpen.value = false
  }
}

function handleSidebarToggleEvent() {
  if (isDesktop.value) {
    collapsed.value = !collapsed.value
    return
  }
  if (!mobileOpen.value && typeof document !== 'undefined' && document.activeElement instanceof HTMLElement) {
    lastFocusedElement = document.activeElement
  }
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

watch(mobileOpen, async (open) => {
  if (isDesktop.value) {
    setBodyScrollLock(false)
    return
  }
  setBodyScrollLock(open)
  if (open) {
    await nextTick()
    mobileCloseButtonRef.value?.focus?.()
    return
  }
  restoreFocusAfterClose()
})

watch(isDesktop, (nextIsDesktop) => {
  if (!nextIsDesktop) return
  mobileOpen.value = false
  setBodyScrollLock(false)
})

onMounted(() => {
  if (typeof window === 'undefined') return
  syncViewportState()
  window.addEventListener('gradtutor:toggle-sidebar', handleSidebarToggleEvent)
  window.addEventListener('gradtutor:close-sidebar', handleSidebarCloseEvent)
  window.addEventListener('resize', syncViewportState)
})

onUnmounted(() => {
  if (typeof window === 'undefined') return
  window.removeEventListener('gradtutor:toggle-sidebar', handleSidebarToggleEvent)
  window.removeEventListener('gradtutor:close-sidebar', handleSidebarCloseEvent)
  window.removeEventListener('resize', syncViewportState)
  setBodyScrollLock(false)
})
</script>
