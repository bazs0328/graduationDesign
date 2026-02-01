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
        class="flex items-center gap-3 px-3 py-2 rounded-md transition-colors hover:bg-accent hover:text-accent-foreground group"
        :class="{ 'bg-accent text-accent-foreground': $route.path === item.path }"
      >
        <component :is="item.icon" class="w-5 h-5" />
        <span v-if="!collapsed" class="font-medium">{{ item.name }}</span>
        <div v-if="collapsed" class="absolute left-16 bg-popover text-popover-foreground px-2 py-1 rounded shadow-md opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50 whitespace-nowrap">
          {{ item.name }}
        </div>
      </router-link>
    </nav>

    <div class="p-4 border-t border-border space-y-4">
      <div v-if="!collapsed" class="space-y-1">
        <label class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">User ID</label>
        <div class="flex gap-2">
          <input
            type="text"
            v-model="userIdLocal"
            class="flex-1 bg-background border border-input rounded px-2 py-1 text-sm focus:ring-2 focus:ring-primary outline-none"
            @blur="updateUserId"
          />
        </div>
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
import { ref, onMounted } from 'vue'
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

const collapsed = ref(false)
const userIdLocal = ref(localStorage.getItem('gradtutor_user') || '')

const navItems = [
  { name: 'Home', path: '/', icon: Home },
  { name: 'Upload', path: '/upload', icon: Upload },
  { name: 'Summary', path: '/summary', icon: FileText },
  { name: 'Q&A', path: '/qa', icon: MessageSquare },
  { name: 'Quiz', path: '/quiz', icon: PenTool },
  { name: 'Progress', path: '/progress', icon: BarChart2 }
]

function updateUserId() {
  if (userIdLocal.value.trim()) {
    localStorage.setItem('gradtutor_user', userIdLocal.value.trim())
    // Trigger a global refresh if needed, for now we just rely on local storage
    window.location.reload() // Simplest way to propagate user change across views
  }
}
</script>
