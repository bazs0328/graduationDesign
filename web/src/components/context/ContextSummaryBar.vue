<template>
  <section
    v-if="items.length || $slots.default"
    data-testid="context-summary-bar"
    class="border px-4 py-3 sm:px-5"
    :class="[containerClass, compact ? 'rounded-[1.05rem]' : 'rounded-[1.25rem]']"
  >
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="space-y-1 min-w-0">
        <div class="flex flex-wrap items-center gap-2 text-[10px] font-bold uppercase tracking-[0.22em]">
          <span
            v-if="sourceTag"
            class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 tracking-[0.18em]"
            :class="sourceTagClass"
          >
            {{ sourceTag }}
          </span>
          <span :class="titleClass">{{ title }}</span>
        </div>
        <p v-if="subtitle" class="text-xs text-muted-foreground leading-relaxed">
          {{ subtitle }}
        </p>
      </div>
      <div v-if="$slots.actions" class="shrink-0">
        <slot name="actions" />
      </div>
    </div>
    <div v-if="items.length" class="mt-3 flex flex-wrap gap-2">
      <span
        v-for="item in items"
        :key="item.label"
        class="workspace-chip"
      >
        <span class="text-muted-foreground">{{ item.label }}</span>
        <span class="font-semibold">{{ item.value }}</span>
      </span>
    </div>
    <div v-if="$slots.default" class="mt-3">
      <slot />
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: {
    type: String,
    default: '当前学习范围',
  },
  sourceTag: {
    type: String,
    default: '',
  },
  subtitle: {
    type: String,
    default: '系统会基于这些资料回答和出题',
  },
  kbName: {
    type: String,
    default: '',
  },
  docName: {
    type: String,
    default: '',
  },
  focus: {
    type: String,
    default: '',
  },
  compact: {
    type: Boolean,
    default: false,
  },
  tone: {
    type: String,
    default: 'info',
    validator: (value) => ['info', 'neutral', 'soft'].includes(value),
  },
})

const items = computed(() => {
  const entries = []
  if (props.kbName) {
    entries.push({ label: '资料库', value: props.kbName })
  }
  if (props.docName) {
    entries.push({ label: '文档', value: props.docName })
  }
  if (props.focus) {
    entries.push({ label: '重点', value: props.focus })
  }
  return entries
})

const containerClass = computed(() => {
  if (props.tone === 'neutral') {
    return 'workspace-toolbar border-border/80 bg-background/82'
  }
  if (props.tone === 'soft') {
    return 'workspace-toolbar border-primary/10 bg-primary/[0.05]'
  }
  return 'workspace-toolbar border-primary/12 bg-[linear-gradient(135deg,rgba(59,130,246,0.08),rgba(255,255,255,0.82))] dark:bg-[linear-gradient(135deg,rgba(59,130,246,0.14),rgba(15,23,42,0.78))]'
})

const titleClass = computed(() => {
  return props.tone === 'neutral' ? 'text-muted-foreground' : 'text-primary/80'
})

const sourceTagClass = computed(() => {
  if (props.tone === 'neutral') {
    return 'border-border bg-card text-muted-foreground'
  }
  return 'border-primary/20 bg-primary/10 text-primary'
})
</script>
