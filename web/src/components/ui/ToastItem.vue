<template>
  <div
    class="flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg backdrop-blur-sm max-w-sm w-full pointer-events-auto transition-all"
    :class="containerClass"
  >
    <component :is="iconComponent" class="w-5 h-5 flex-shrink-0 mt-0.5" />
    <p class="flex-1 text-sm font-medium leading-snug">{{ toast.message }}</p>
    <button
      v-if="toast.type === 'error'"
      class="flex-shrink-0 p-0.5 rounded hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
      @click="$emit('close')"
    >
      <X class="w-4 h-4" />
    </button>
    <div
      v-if="toast.duration > 0"
      class="absolute bottom-0 left-0 h-0.5 rounded-b-xl origin-left"
      :class="progressClass"
      :style="{ animation: `toast-shrink ${toast.duration}ms linear forwards` }"
    ></div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-vue-next'

const props = defineProps({
  toast: { type: Object, required: true },
})

defineEmits(['close'])

const STYLES = {
  success: {
    container: 'bg-emerald-50/95 border-emerald-200 text-emerald-900 dark:bg-emerald-500/12 dark:border-emerald-400/20 dark:text-emerald-100',
    icon: CheckCircle,
    progress: 'bg-green-500',
  },
  error: {
    container: 'bg-red-50/95 border-red-200 text-red-900 dark:bg-red-500/12 dark:border-red-400/20 dark:text-red-100',
    icon: XCircle,
    progress: 'bg-red-500',
  },
  warning: {
    container: 'bg-amber-50/95 border-amber-200 text-amber-900 dark:bg-amber-500/12 dark:border-amber-400/20 dark:text-amber-100',
    icon: AlertTriangle,
    progress: 'bg-amber-500',
  },
  info: {
    container: 'bg-sky-50/95 border-sky-200 text-sky-900 dark:bg-sky-500/12 dark:border-sky-400/20 dark:text-sky-100',
    icon: Info,
    progress: 'bg-blue-500',
  },
}

const style = computed(() => STYLES[props.toast.type] || STYLES.info)
const containerClass = computed(() => style.value.container)
const iconComponent = computed(() => style.value.icon)
const progressClass = computed(() => style.value.progress)
</script>
