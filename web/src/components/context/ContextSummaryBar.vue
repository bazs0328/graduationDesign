<template>
  <section
    v-if="items.length"
    class="rounded-2xl border border-primary/15 bg-gradient-to-r from-primary/8 via-background to-background px-4 py-3 sm:px-5"
  >
    <div class="flex flex-wrap items-center gap-2 text-[10px] font-bold uppercase tracking-[0.22em] text-primary/80">
      <span>{{ title }}</span>
      <span class="h-px w-8 bg-primary/20"></span>
      <span class="text-muted-foreground">{{ subtitle }}</span>
    </div>
    <div class="mt-3 flex flex-wrap gap-2">
      <span
        v-for="item in items"
        :key="item.label"
        class="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-xs text-foreground shadow-sm"
      >
        <span class="text-muted-foreground">{{ item.label }}</span>
        <span class="font-semibold">{{ item.value }}</span>
      </span>
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
</script>
