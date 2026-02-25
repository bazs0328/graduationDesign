<template>
  <teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-[70] bg-black/70 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6"
      @click.self="emitClose"
    >
      <section
        class="w-full max-w-5xl bg-card border border-border rounded-2xl shadow-xl overflow-hidden"
        role="dialog"
        aria-modal="true"
        :aria-label="title || '图片预览'"
      >
        <header class="px-4 sm:px-5 py-3 sm:py-4 border-b border-border flex items-start justify-between gap-4">
          <div class="space-y-1 min-w-0">
            <h3 class="text-base sm:text-lg font-bold text-foreground truncate">
              {{ title || '图片预览' }}
            </h3>
            <p v-if="caption" class="text-xs sm:text-sm text-muted-foreground line-clamp-2">
              {{ caption }}
            </p>
          </div>
          <button
            ref="closeButtonRef"
            type="button"
            class="shrink-0 text-sm px-3 py-1.5 rounded-lg border border-border hover:bg-accent"
            @click="emitClose"
          >
            关闭
          </button>
        </header>

        <div class="p-3 sm:p-5 max-h-[80vh] overflow-auto bg-background/50">
          <div v-if="src" class="rounded-xl border border-border bg-background p-2 sm:p-3">
            <img
              :src="src"
              :alt="alt || caption || '预览图片'"
              class="w-full max-h-[70vh] object-contain rounded-lg bg-muted/20"
              loading="lazy"
            />
          </div>
          <div v-else class="text-sm text-muted-foreground">暂无可预览图片。</div>
        </div>
      </section>
    </div>
  </teleport>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  src: { type: String, default: '' },
  alt: { type: String, default: '' },
  caption: { type: String, default: '' },
  title: { type: String, default: '' },
})

const emit = defineEmits(['close'])

const closeButtonRef = ref(null)
let lastActiveElement = null

function emitClose() {
  emit('close')
}

function onKeydown(event) {
  if (!props.open) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emitClose()
  }
}

function attachListener() {
  window.addEventListener('keydown', onKeydown)
}

function detachListener() {
  window.removeEventListener('keydown', onKeydown)
}

watch(
  () => props.open,
  async (open) => {
    if (open) {
      lastActiveElement = document.activeElement instanceof HTMLElement ? document.activeElement : null
      attachListener()
      await nextTick()
      if (closeButtonRef.value instanceof HTMLElement) {
        closeButtonRef.value.focus()
      }
      return
    }
    detachListener()
    if (lastActiveElement instanceof HTMLElement) {
      try {
        lastActiveElement.focus()
      } catch {
        // ignore focus restore failures
      }
    }
    lastActiveElement = null
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  detachListener()
})
</script>

