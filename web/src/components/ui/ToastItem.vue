<template>
  <div
    class="flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg backdrop-blur-sm max-w-sm w-full pointer-events-auto transition-all"
    :class="containerClass"
  >
    <component :is="iconComponent" class="w-5 h-5 flex-shrink-0 mt-0.5" />
    <p class="flex-1 text-sm font-medium leading-snug">{{ toast.message }}</p>
    <button
      v-if="toast.type === 'error'"
      class="flex-shrink-0 p-0.5 rounded hover:bg-black/10 transition-colors"
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
    container: 'bg-green-50 border-green-200 text-green-800',
    icon: CheckCircle,
    progress: 'bg-green-500',
  },
  error: {
    container: 'bg-red-50 border-red-200 text-red-800',
    icon: XCircle,
    progress: 'bg-red-500',
  },
  warning: {
    container: 'bg-amber-50 border-amber-200 text-amber-800',
    icon: AlertTriangle,
    progress: 'bg-amber-500',
  },
  info: {
    container: 'bg-blue-50 border-blue-200 text-blue-800',
    icon: Info,
    progress: 'bg-blue-500',
  },
}

const style = computed(() => STYLES[props.toast.type] || STYLES.info)
const containerClass = computed(() => style.value.container)
const iconComponent = computed(() => style.value.icon)
const progressClass = computed(() => style.value.progress)
</script>
