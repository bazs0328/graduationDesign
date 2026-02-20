<template>
  <teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4"
      @click.self="$emit('close')"
    >
      <section class="w-full max-w-3xl bg-card border border-border rounded-2xl shadow-xl overflow-hidden">
        <header class="px-5 py-4 border-b border-border flex items-start justify-between gap-4">
          <div class="space-y-1">
            <h3 class="text-lg font-bold text-foreground">{{ title || '来源预览' }}</h3>
            <p class="text-xs text-muted-foreground" v-if="sourceLabel || page || chunk">
              <span v-if="sourceLabel">{{ sourceLabel }}</span>
              <span v-if="page"> · p.{{ page }}</span>
              <span v-if="chunk"> · c.{{ chunk }}</span>
            </p>
          </div>
          <button
            class="shrink-0 text-sm px-3 py-1.5 rounded-lg border border-border hover:bg-accent"
            @click="$emit('close')"
          >
            关闭
          </button>
        </header>

        <div class="px-5 py-5 max-h-[70vh] overflow-auto">
          <div v-if="loading" class="text-sm text-muted-foreground">正在加载原文片段...</div>
          <div v-else-if="error" class="text-sm text-destructive">{{ error }}</div>
          <pre
            v-else
            class="whitespace-pre-wrap text-sm leading-7 text-foreground bg-background border border-border rounded-xl p-4"
          >{{ snippet || '暂无可预览内容。' }}</pre>
        </div>
      </section>
    </div>
  </teleport>
</template>

<script setup>
defineProps({
  open: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  title: { type: String, default: '' },
  sourceLabel: { type: String, default: '' },
  page: { type: Number, default: null },
  chunk: { type: Number, default: null },
  snippet: { type: String, default: '' },
  error: { type: String, default: '' },
})

defineEmits(['close'])
</script>
