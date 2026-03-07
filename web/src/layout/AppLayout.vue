<template>
  <div class="flex h-screen bg-background text-foreground overflow-hidden">
    <AppSidebar />
    <main class="flex-1 flex flex-col min-w-0 overflow-hidden">
      <header class="border-b border-border/70 bg-background/72 backdrop-blur-xl">
        <div class="flex items-center justify-between gap-4 px-4 py-3 md:px-6 lg:px-8">
          <div class="min-w-0 flex items-center gap-3">
            <div class="flex items-center gap-2 min-w-0">
              <button
                type="button"
                class="lg:hidden p-2 rounded-full hover:bg-accent transition-colors"
                @click="toggleSidebarDrawer"
                aria-label="打开导航菜单"
              >
                <PanelLeft class="w-5 h-5" />
              </button>
              <div class="min-w-0">
                <p class="text-[10px] font-bold uppercase tracking-[0.28em] text-muted-foreground">GradTutor Workspace</p>
                <h2 class="text-base md:text-lg font-semibold truncate">{{ currentRouteName }}</h2>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2 md:gap-4 flex-shrink-0">
            <button
            @click="toggleTheme"
            class="inline-flex items-center gap-2 px-2.5 py-2 rounded-full hover:bg-accent transition-colors text-sm"
            title="切换主题"
            aria-label="切换主题"
          >
            <component :is="isDark ? Sun : Moon" class="w-5 h-5" />
            <span class="hidden md:inline font-medium">{{ isDark ? '浅色' : '深色' }}</span>
          </button>
            <div class="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-card/80 border border-border rounded-full text-sm font-medium shadow-sm">
              <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              {{ displayName }}
            </div>
          </div>
        </div>
      </header>
      <div class="flex-1 overflow-y-auto">
        <div class="px-4 py-5 md:px-6 md:py-6 lg:px-8 lg:py-8">
        <ProviderSetupNotice
          v-if="showProviderSetupBanner"
          class="mb-6"
          compact
          title="先完成模型接入配置"
          description="当前模型接入还没准备好。完成设置后，摘要、问答和测验会自动恢复可用。"
          :missing="providerSetupMissing"
        />
        <router-view v-slot="{ Component }">
          <transition name="fade">
            <keep-alive>
              <component :is="Component" />
            </keep-alive>
          </transition>
        </router-view>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Sun, Moon, PanelLeft } from 'lucide-vue-next'
import AppSidebar from './AppSidebar.vue'
import { getCurrentUser } from '../api'
import { hasAccessToken } from '../composables/useAuthSession'
import { useTheme } from '../composables/useTheme'
import { useAppContextStore } from '../stores/appContext'
import { useSettingsStore } from '../stores/settings'
import ProviderSetupNotice from '../components/settings/ProviderSetupNotice.vue'

const route = useRoute()
const { isDark, toggleTheme } = useTheme()
const appContext = useAppContextStore()
const settingsStore = useSettingsStore()
appContext.hydrate()

const displayName = computed(() => {
  const user = getCurrentUser()
  return user ? (user.name || user.username) : '游客'
})

const currentRouteName = computed(() => {
  return route.meta?.title || route.name || '控制台'
})

const providerSetup = computed(() => settingsStore.providerSetup)
const providerSetupMissing = computed(() => providerSetup.value?.missing || [])
const showProviderSetupBanner = computed(() => {
  if (route.path === '/settings') return false
  const setup = providerSetup.value
  if (!setup) return false
  return !setup.llm_ready || !setup.embedding_ready
})

function toggleSidebarDrawer() {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent('gradtutor:toggle-sidebar'))
}

onMounted(async () => {
  if (!hasAccessToken()) return
  try {
    await appContext.loadKbs()
  } catch {
    // ignore header-only context load failures
  }
  try {
    await settingsStore.load({
      userId: appContext.resolvedUserId || 'default',
      kbId: appContext.selectedKbId || '',
    })
  } catch {
    // ignore layout-level settings load failures
  }
})

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
