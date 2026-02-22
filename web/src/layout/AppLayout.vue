<template>
  <div class="flex h-screen bg-background text-foreground overflow-hidden">
    <AppSidebar />
    <main class="flex-1 flex flex-col min-w-0 overflow-hidden">
      <header class="h-16 border-b border-border flex items-center justify-between px-4 md:px-6 lg:px-8 bg-card/50 backdrop-blur-sm gap-3">
        <div class="flex items-center gap-2 min-w-0">
          <button
            type="button"
            class="lg:hidden p-2 rounded-full hover:bg-accent transition-colors"
            @click="toggleSidebarDrawer"
            aria-label="打开导航菜单"
          >
            <PanelLeft class="w-5 h-5" />
          </button>
          <h2 class="text-base md:text-lg font-semibold truncate">{{ currentRouteName }}</h2>
        </div>
        <div class="flex items-center gap-2 md:gap-4 flex-shrink-0">
          <button
            @click="toggleTheme"
            class="inline-flex items-center gap-2 px-2.5 py-2 rounded-full hover:bg-accent transition-colors text-sm"
            title="切换主题"
            aria-label="切换主题"
          >
            <component :is="isDark ? 'Sun' : 'Moon'" class="w-5 h-5" />
            <span class="hidden md:inline font-medium">{{ isDark ? '浅色' : '深色' }}</span>
          </button>
          <div class="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-accent rounded-full text-sm font-medium">
            <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
            {{ displayName }}
          </div>
        </div>
      </header>
      <div class="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
        <router-view v-slot="{ Component }">
          <keep-alive>
            <transition name="fade" mode="out-in">
              <component :is="Component" />
            </transition>
          </keep-alive>
        </router-view>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Sun, Moon, PanelLeft } from 'lucide-vue-next'
import AppSidebar from './AppSidebar.vue'
import { getCurrentUser } from '../api'

const THEME_STORAGE_KEY = 'gradtutor_theme'
const route = useRoute()
const isDark = ref(readThemeFromDom())

const displayName = computed(() => {
  const user = getCurrentUser()
  return user ? (user.name || user.username) : '游客'
})

const currentRouteName = computed(() => {
  return route.meta?.title || route.name || '控制台'
})

function readThemeFromDom() {
  if (typeof document === 'undefined') return false
  return document.documentElement.classList.contains('dark')
}

function applyTheme(theme) {
  if (typeof document === 'undefined') return
  const resolved = theme === 'dark' ? 'dark' : 'light'
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
  root.classList.toggle('light', resolved === 'light')
}

function toggleTheme() {
  const nextTheme = isDark.value ? 'light' : 'dark'
  isDark.value = nextTheme === 'dark'
  applyTheme(nextTheme)
  try {
    localStorage.setItem(THEME_STORAGE_KEY, nextTheme)
  } catch {
    // ignore localStorage access errors
  }
}

function toggleSidebarDrawer() {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent('gradtutor:toggle-sidebar'))
}

</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
