<template>
  <section class="rounded-2xl border border-border bg-card/95 shadow-sm overflow-hidden">
    <button
      type="button"
      class="w-full px-4 py-3 sm:px-5 sm:py-4 flex items-start justify-between gap-4 text-left hover:bg-accent/40 transition-colors"
      :aria-expanded="openState ? 'true' : 'false'"
      @click="toggle"
    >
      <div class="space-y-1 min-w-0">
        <p class="text-[10px] font-bold uppercase tracking-[0.24em] text-primary/80">{{ eyebrow }}</p>
        <h3 class="text-sm sm:text-base font-bold tracking-tight">{{ title }}</h3>
        <p v-if="description" class="text-xs sm:text-sm text-muted-foreground leading-relaxed">
          {{ description }}
        </p>
      </div>
      <span class="shrink-0 inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-border bg-background text-[11px] font-semibold text-muted-foreground">
        {{ openState ? collapseLabel : expandLabel }}
        <ChevronDown class="w-3.5 h-3.5 transition-transform" :class="openState ? 'rotate-180' : ''" />
      </span>
    </button>

    <div v-if="openState" class="px-4 pb-4 sm:px-5 sm:pb-5 border-t border-border/70 bg-background/35">
      <div class="pt-4 space-y-4 min-w-0" :class="contentClass">
        <slot />
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ChevronDown } from 'lucide-vue-next'

const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  description: {
    type: String,
    default: '',
  },
  eyebrow: {
    type: String,
    default: '高级选项',
  },
  defaultOpen: {
    type: Boolean,
    default: false,
  },
  contentClass: {
    type: String,
    default: '',
  },
  expandLabel: {
    type: String,
    default: '展开',
  },
  collapseLabel: {
    type: String,
    default: '收起',
  },
})

const emit = defineEmits(['update:open'])
const openState = ref(Boolean(props.defaultOpen))

watch(
  () => props.defaultOpen,
  (nextValue) => {
    openState.value = Boolean(nextValue)
  }
)

function toggle() {
  openState.value = !openState.value
  emit('update:open', openState.value)
}
</script>
