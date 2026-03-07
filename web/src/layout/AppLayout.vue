<template>
  <div class="flex h-screen bg-background text-foreground overflow-hidden">
    <AppSidebar />
    <main class="flex-1 flex flex-col min-w-0 overflow-hidden">
      <header class="border-b border-border px-4 py-3 md:px-6 lg:px-8 bg-card/50 backdrop-blur-sm">
        <div class="flex items-start justify-between gap-4">
          <div class="min-w-0 flex-1 space-y-3">
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
                <p class="text-[10px] font-bold uppercase tracking-[0.24em] text-muted-foreground">GradTutor</p>
                <h2 class="text-base md:text-lg font-semibold truncate">{{ currentRouteName }}</h2>
              </div>
            </div>
            <ContextSummaryBar
              v-if="showHeaderContextBar"
              :kb-name="selectedKbName"
              :doc-name="selectedDocName"
              subtitle="当前资料范围会在问答、摘要和测验中自动沿用"
            />
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
            <div class="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-accent rounded-full text-sm font-medium">
              <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              {{ displayName }}
            </div>
          </div>
        </div>
      </header>
      <div class="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
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
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Sun, Moon, PanelLeft } from 'lucide-vue-next'
import AppSidebar from './AppSidebar.vue'
import { getCurrentUser } from '../api'
import { hasAccessToken } from '../composables/useAuthSession'
import { useTheme } from '../composables/useTheme'
import { useAppContextStore } from '../stores/appContext'
import { useSettingsStore } from '../stores/settings'
import { useKbDocuments } from '../composables/useKbDocuments'
import ContextSummaryBar from '../components/context/ContextSummaryBar.vue'
import ProviderSetupNotice from '../components/settings/ProviderSetupNotice.vue'

const route = useRoute()
const { isDark, toggleTheme } = useTheme()
const appContext = useAppContextStore()
const settingsStore = useSettingsStore()
appContext.hydrate()
const kbDocs = useKbDocuments({
  userId: computed(() => appContext.resolvedUserId || 'default'),
  kbId: computed(() => appContext.selectedKbId || ''),
})

const displayName = computed(() => {
  const user = getCurrentUser()
  return user ? (user.name || user.username) : '游客'
})

const currentRouteName = computed(() => {
  return route.meta?.title || route.name || '控制台'
})

const selectedKbName = computed(() => {
  const currentKb = appContext.kbs.find((item) => item.id === appContext.selectedKbId)
  return currentKb?.name || ''
})

const selectedDocName = computed(() => {
  const currentDoc = kbDocs.docs.value.find((item) => item.id === appContext.selectedDocId)
  return currentDoc?.filename || ''
})

const providerSetup = computed(() => settingsStore.providerSetup)
const providerSetupMissing = computed(() => providerSetup.value?.missing || [])
const showHeaderContextBar = computed(() => route.meta?.showHeaderContextBar !== false)
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
  if (appContext.selectedKbId) {
    try {
      await kbDocs.refresh()
    } catch {
      // ignore header-only context load failures
    }
  }
})

watch(
  () => appContext.selectedKbId,
  async (nextKbId) => {
    if (!hasAccessToken()) {
      kbDocs.reset()
      return
    }
    if (!nextKbId) {
      kbDocs.reset()
      return
    }
    try {
      await kbDocs.refresh()
    } catch {
      // ignore header-only context load failures
    }
  }
)

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
