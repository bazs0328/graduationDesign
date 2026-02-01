<template>
  <div class="flex h-screen bg-background text-foreground overflow-hidden">
    <AppSidebar />
    <main class="flex-1 flex flex-col min-w-0 overflow-hidden">
      <header class="h-16 border-b border-border flex items-center justify-between px-8 bg-card/50 backdrop-blur-sm">
        <h2 class="text-lg font-semibold">{{ currentRouteName }}</h2>
        <div class="flex items-center gap-4">
          <button @click="toggleTheme" class="p-2 rounded-full hover:bg-accent transition-colors">
            <component :is="isDark ? 'Sun' : 'Moon'" class="w-5 h-5" />
          </button>
          <div class="flex items-center gap-2 px-3 py-1.5 bg-accent rounded-full text-sm font-medium">
            <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
            {{ userId }}
          </div>
        </div>
      </header>
      <div class="flex-1 overflow-y-auto p-8">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Sun, Moon } from 'lucide-vue-next'
import AppSidebar from './AppSidebar.vue'

const route = useRoute()
const isDark = ref(true)
const userId = ref(localStorage.getItem('gradtutor_user') || 'Guest')

const currentRouteName = computed(() => {
  return route.name || 'Dashboard'
})

function toggleTheme() {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('light', !isDark.value)
}

onMounted(() => {
  // Initialize theme
  document.documentElement.classList.toggle('light', !isDark.value)
})

// Listen for storage changes to update userId
window.addEventListener('storage', () => {
  userId.value = localStorage.getItem('gradtutor_user') || 'Guest'
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
